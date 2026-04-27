import scrapy
import asyncio
import copy
import enum
from fileinput import filename
import scrapy
from scrapy.http import HtmlResponse
import json
from datetime import datetime, time
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from model import JobPost, Location, Compensation, Country


DEBUG = False
DEBUG_COMPANY_URLS = False
DEBUG_DESCRIPTION = False
DEPTH =  10
class JobteaserSpider(scrapy.Spider):
    name = "jobteaser"
    allowed_domains = ["www.jobteaser.com"]
    start_urls = ["https://www.jobteaser.com/"]
    
    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
        'DOWNLOAD_HANDLERS': {
            'http': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
            'https': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
        },
        'TWISTED_REACTOR': 'twisted.internet.asyncioreactor.AsyncioSelectorReactor',
        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
        'PLAYWRIGHT_LAUNCH_OPTIONS': {
            'headless': True,
            'args': [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            ],
        },
        'PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT': 30000,
        "MONGO_DATABASE": "jobs_jobteaser", 
    }
    
    def __init__(self, query: str = "", country: str = "France", contract_type: str = "internship", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query
        self.country = "France"
        self.contract_type = contract_type
        self.base_url = "https://www.jobteaser.com/fr/job-offers"
        self.job_log_file = "job_link_mapping.txt"

    def start_requests(self):
        params = {
            "q": self.query,  # ex: "sécurité informatique"
            "contract": "internship",  # ex: "internship"
            "lat": "46.711046",  # 46.711046
            "lng": "2.181179",  # 2.181179
            "localized_location": self.country,  # "France"
            "location": self.country,  # "France"
            "page": 1,
        }
        url = f"{self.base_url}?{urlencode(params, doseq=True)}"
        if DEBUG : 
            with open("url.txt", "w") as f:
                f.write(url + "\n")
        yield scrapy.Request(
            url,
            meta={
                'playwright': True,
                'playwright_include_page': True,
                'page': 1,
                'url': url,
            },
            callback=self.parse_search_page,
            errback=self.errback_close_page,
        )

    async def parse_search_page(self, response):
        page = response.meta['playwright_page']
        current_page = response.meta.get('page', 1)
        url = response.meta.get('url')
        try:
            await page.wait_for_load_state('domcontentloaded')
            #await page.wait_for_load_state('networkidle')
            await page.wait_for_selector('a[href*="/fr/job-offers/"]', timeout=20000)
            #await page.wait_for_selector('a[class^="JobAdCard_link"]', state="visible", timeout=10000)
            content = await page.content()
            rendered = HtmlResponse(url=response.url, body=content, encoding='utf-8')

            job_links = rendered.xpath(
                '//a[contains(@href, "/fr/job-offers/")]/@href'
            ).getall()
            job_links = list(set(job_links))  # Remove duplicates
            if DEBUG : 
                with open("job_links_Jobteaser.txt", "a") as f:
                  f.write("\n".join(job_links))
            # import time
            # time.sleep(10)  # Add a small delay to be polite to the server
            if not job_links:
                self.logger.info("No job links found. Stopping.")
                return
            
            for link in job_links:
                yield scrapy.Request(
                    rendered.urljoin(link),
                    meta=   {
                            'playwright': True,
                            'playwright_include_page': True,
                            'playwright_page_methods': [
                            # Wait until the document is fully loaded
                            {"name": "wait_for_load_state", "args": ["domcontentloaded"]},
                            # Optional: add a timeout (in milliseconds) for the page to load
                            {"name": "set_default_navigation_timeout", "args": [30000]}  # 30 seconds
                        ], 
                            },
                    callback=self.parse_job_detail,
                    errback=self.errback_close_page,
                )
            next_page = current_page + 1
            params = {
            "refinementList[offices.country_code][]": self.country,
            "refinementList[contract_type][]": self.contract_type,
            "query": self.query,
            "page": next_page,
            }
            next_link = f"{self.base_url}?{urlencode(params, doseq=True)}"
            if DEBUG : 
                with open("next_link.txt", "a") as f:
                  f.write(next_link +"\n")
            if next_link and current_page < DEPTH:
                yield scrapy.Request(
                    rendered.urljoin(next_link),
                    meta={
                        'playwright': True,
                        'playwright_include_page': True,
                        'page': response.meta.get('page', 1) + 1,
                    },
                    callback=self.parse_search_page,
                    errback=self.errback_close_page,
                )
        except Exception as e:
            self.logger.error(f"Error parsing search page {response.url}: {e}")
        finally:
            await page.close()

    async def parse_job_detail(self, response):
        page = response.meta['playwright_page']
        filename = f"{response.meta.get('indice')}"
        
        print(f"Parsing job detail page: {response.url}")
        try:
            await page.wait_for_load_state('domcontentloaded')
            #await page.wait_for_load_state('networkidle')

            current_url = page.url
          
            if '/404' in current_url or 'error' in current_url:
                self.logger.warning(f"Page redirected to error: {current_url}")
                if DEBUG : 
                    with open("failed_urls.html", "a", encoding="utf-8") as f:
                        f.write(f"Page redirected to error: {current_url}\n")
                return

            # Wait for the metadata block to be present
            try:
                await page.wait_for_selector('[id="job-ad-detail-content"]', timeout=20000)
            except Exception:
                self.logger.warning(f"job-ad-detail-content not found at {response.url}")
                if DEBUG : 
                    with open("failed_metadatablocks.html", "a", encoding="utf-8") as f:
                        f.write(f"job-ad-detail-content not found at {response.url}\n")
                return

            content = await page.content()
            if DEBUG : 
                with open(f"debug_{filename}.html", "w", encoding="utf-8") as f:
                   f.write(content)

            rendered = HtmlResponse(url=response.url, body=content, encoding='utf-8')

            metadata_block = rendered.css('[id="job-ad-detail-content"]')

            # --- Job title ---
            title = metadata_block.css('h1[data-testid="jobad-DetailView__Heading__title"] ::text').get('').strip()

            # --- Company name & URL ---
            
            company_name = metadata_block.css('h2[data-testid="jobad-DetailView__Heading__company_name"]::text').get(default='').strip()
            company_relative_url = metadata_block.css('a[href*="/companies/"] ::attr(href)').get()
            company_url = f"https://www.jobteaser.com{company_relative_url}"
            # scrapping company profile page
            
            # --- Company logo ---
            company_logo = metadata_block.css('img[alt]::attr(src)').get('')

            # --- Metadata tags (contract, location, remote, salary) ---
            #tags = metadata_block.css('div.sc-fibHhp')

            contract_type = None
            contract_duration = metadata_block.css('p[data-testid="jobad-DetailView__CandidacyDetails__contract"] ::text').get('').strip()
            #jobad-DetailView__CandidacyDetails__Locations
            location = metadata_block.css('p[data-testid="jobad-DetailView__CandidacyDetails__Locations ::text"]').get('').strip()
            remote_type = metadata_block.css('p[data-testid="jobad-DetailView__CandidacyDetails__RemotePolicy"] ::text').get('').strip()
            salary = metadata_block.css('p[data-testid="jobad-DetailView__CandidacyDetails__Wage"] ::text').get('').strip()
            starting_date = metadata_block.css('p[data-testid="jobad-DetailView__CandidacyDetails__start_date ::text"]').get('').strip()

           
            # --- Apply URL ---
            # apply_url = metadata_block.css(
            #     'a[data-testid="job_header-button-apply"]::attr(href)'
            # ).get('')

            # --- Date posted ---
            #date_posted_raw = metadata_block.css('time::attr(datetime)').get('')
            date_posted = metadata_block.css('p.PageHeader_publicationDate__X1f53::text').get(default='').strip()
            # if date_posted_raw:
            #     try:
            #         from datetime import datetime
            #         date_posted = datetime.fromisoformat(
            #             date_posted_raw.replace("Z", "+00:00")
            #         ).date()
            #     except Exception:
            #         pass

            # --- Job description ---
            # description_html = await page.evaluate('''() => {
            #     const el = document.querySelector('[id="description-summary-block"]');
            #     return el ? el.innerHTML : "";
            # }''')
            description_text = "\n\n".join(
                response.css('article[data-testid="jobad-DetailView__Description"] .sk-Text ::text').getall()
            )
            

            # --- Profile / experience required ---
            # profile_html = await page.evaluate('''() => {
            #     const el = document.querySelector('[data-testid="job-section-experience"] [data-is-text-too-long]');
            #     return el ? el.innerHTML : "";
            # }''')
                        # Build result dict (adapt to your JobPost model as needed)
            job_post_data = {
                "origine": "Jobteaser",
                "title": title,
                "company_name": company_name,
                "company_url": company_url,
                "company_logo": company_logo,
                "job_url": response.url,
                #"apply_url": apply_url,
                "location": location,
                "contract_type": contract_type,
                "contract_duration": contract_duration,
                "remote_type": remote_type,
                "salary": salary,
                "date_posted": str(date_posted) if date_posted else None,
                "description": description_text,
              
            }

            self.logger.info(f"Scraped job: {title} @ {company_name}")

            # Yield as JobPost if your model supports it, otherwise yield dict
            try:
               

                job_post = JobPost(
                    origine="Jobteaser",
                    id=None,
                    title=title,
                    company_name=company_name,
                    job_url=response.url,
                    job_url_direct=None,
                    location=location,
                    description=description_text,
                    company_url=company_url,
                    company_url_direct=company_url,
                    compensation=None,
                    date_posted=str(date_posted) if date_posted else None,
                    is_remote=bool(remote_type and 'télétravail' in remote_type.lower()),
                    listing_type=contract_type,
                    job_level=None,
                    job_function=None,
                    skills=None,
                    experience_range=None,
                    company_logo=company_logo,
                    company_description=None,
                    emails=None,
                    company_addresses=None,
                    company_num_employees=None,
                    company_revenue=None,
                    banner_photo_url=None,
                    company_rating=None,
                    company_reviews_count=None,
                    vacancy_count=None,
                    work_from_home_type=remote_type,
                    company_industry=None,
                    salary=salary,
                    starting_date=starting_date,
                    company_slogans=None,
                    company_followers=None,
                    company_type=None,
                    company_social_links=None,
                    profile=None,
                    credibility_score = None,
                    label = None,
                    credibility_flags = None,
                    s1_score          = None,
                    s1_details        = None,
                    s4_score          = None,
                    s4_details        = None,
                    s3_score          = None,
                    s3_details        = None,
                    scored_at         = None
                )
                #yield job_post
            except Exception as e:
                self.logger.error(f"JobPost build error: {e}")
                if DEBUG : 
                    with open("jobpost_errors.txt", "a", encoding="utf-8") as f:
                        f.write(f"Error building JobPost for {response.url}: {e}\n")
                #yield job_post_data
            if DEBUG_COMPANY_URLS : 
                with open("company_urls.txt", "a", encoding="utf-8") as f:
                    f.write(company_relative_url + "\n" )
            if company_url:
                yield scrapy.Request(
                    company_url,
                    meta={
                        'playwright': True,
                        'playwright_include_page': True,
                        'job_post': copy.deepcopy(job_post),
                    },
                    callback=self.parse_company_page,
                    errback=self.errback_close_page,
                    dont_filter=True,
                )
            #yield job_post
            else:
                #yield job_post
                pass
        except Exception as e:
            self.logger.error(f"Error parsing job detail {response.url}: {e}")
        finally:
            await page.close()
    async def parse_company_page(self, response):
        page = response.meta['playwright_page']
        job_post = response.meta['job_post']
       
    
        try:
            await page.wait_for_load_state('domcontentloaded')
            ##await page.wait_for_load_state('networkidle')

            # try:
            #     await page.wait_for_selector(
            #         '[data-testid="organization-page-profile-sidebar"]',
            #         timeout=15000
            #     )
            # except Exception:
            #     self.logger.warning(f"Company sidebar not found at {response.url}")
            #     yield job_post
            #     return

            content = await page.content()
            rendered = HtmlResponse(url=response.url, body=content, encoding='utf-8')

            # --- Company website ---
            company_website = rendered.css(
                '[data-testid="company_header_website_link"]::attr(href)'
            ).get('').strip()
            company_slogan = rendered.css(
                '[data-testid="company_header_description"] ::text'
            ).get('').strip()
            company_type = rendered.css(
                '[data-testid="company_header_business_type"] ::text'
            ).get('').strip()
            company_followers = rendered.css(
                '[data-testid="company_header_followers_unlogged"] ::text'
            ).get('').strip()
            # --- Company sector ---
            company_sector = rendered.css(
                '[data-testid="company_header_sector"] ::text'
            ).get('').strip()

            # --- Company location ---
            company_location = rendered.css(
                '[data-testid="company_header_address"] ::text'
            ).get('').strip()

            # --- Social media links ---

       
            social_links = rendered.css('[data-testid="company_social_networks"] a::attr(href)').getall()
            

        
            # Use Playwright for more reliable block extraction
            company_description = "\n\n".join(
                response.css('div[data-testid="company_information_what_content"]  *::text').getall()
            )
            if DEBUG_DESCRIPTION :
                with open(f"description_{filename}.txt", "a", encoding="utf-8") as f:
                    f.write(company_description)

            # Social links via Playwright for reliability
            # social_links_js = await page.evaluate('''() => {
            #     const networks = ['linkedin', 'twitter', 'facebook', 
            #                     'instagram', 'youtube', 'tiktok'];
            #     const result = {};
            #     networks.forEach(network => {
            #         const el = document.querySelector(
            #             `[data-testid="social-network-${network}"]`
            #         );
            #         if (el) result[network] = el.getAttribute('href');
            #     });
            #     return result;
            # }''')

            self.logger.info(
                f"Company page scraped: {response.url} | "
                f"Website: {company_website} | "
                f"Sector: {company_sector} | "
                f"Location: {company_location} | "
                #f"Social: {social_links_js} | "
            )

            # --- Enrich the job_post with company data ---
            job_post["company_url_direct"] = company_website or job_post.get("company_url_direct")
            job_post["company_industry"] = company_sector or job_post.get("company_industry")
            job_post["company_addresses"] = company_location or job_post.get("company_addresses")
            job_post["company_social_links"] = social_links or job_post.get("company_social_links")
            job_post["company_description"] = company_description
            job_post["company_slogans"] = company_slogan or job_post.get("company_slogans")
            job_post["company_followers"] = company_followers or job_post.get("company_followers")
            job_post["company_type"] = company_type or job_post.get("company_type")

            self.logger.info(f"Social links: {social_links}")

            yield job_post

        except Exception as e:
            self.logger.error(f"Error parsing company page {response.url}: {e}")
            yield job_post
        finally:
            await page.close()

   
    async def errback_close_page(self, failure):
        page = failure.request.meta.get('playwright_page')
        job_post = failure.request.meta.get('job_post')  # ← recover the job
        if page:
            await page.close()
        if job_post:
            self.logger.warning(f"Request failed, yielding job anyway: {failure.request.url}")
            yield job_post  # ← don't lose the job on error