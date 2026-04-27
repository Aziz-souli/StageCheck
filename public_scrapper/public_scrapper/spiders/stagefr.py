import scrapy
import random
import copy
import scrapy
from scrapy.http import HtmlResponse
import json
from datetime import datetime, time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from model import JobPost, Location, Compensation, Country
DEBUG = False
DEBUG_NEXT_LINKS = False
DEBUG_COMPANY_URLS = False
DEBUG_DESCRIPTION = False
DEPTH_LIMIT =  10
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
]

class StagefrSpider(scrapy.Spider):
    name = "stagefr"
    allowed_domains = ["www.stage.fr"]
    start_urls = ["https://www.stage.fr/"]
    
    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
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
        "MONGO_DATABASE": "jobs_Stagefr", 
        
    }
    
    def __init__(self, query: str = "", country: str = "France", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query
        self.country = country
        self.base_url = "https://www.stage.fr/jobs"
        self.job_log_file = "job_link_mapping.txt"

    def start_requests(self):
        params = {
            "q": self.query,  # ex: "sécurité informatique"
            "l": self.country,  # ex: "France"
            "job_type[]": "STAGE",
            "p": 1,
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
                'playwright_context_kwargs': {
                    # 'user_agent': random.choice(USER_AGENTS),
                    'user_agent': USER_AGENTS[3],

                }
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
            await page.wait_for_selector('a[href*="/job/"]', timeout=20000)
            content = await page.content()
            rendered = HtmlResponse(url=response.url, body=content, encoding='utf-8')

            job_links = rendered.xpath(
                '//a[contains(@href, "/job/")]/@href'
            ).getall()
            job_links = list(set(job_links))  # Remove duplicates
            if DEBUG : 
                with open("job_links_Stagefr.txt", "a") as f:
                  f.write("\n".join(job_links))
            # import time
            # time.sleep(10)  # Add a small delay to be polite to the server
            if not job_links:
                self.logger.info("No job links found. Stopping.")
                return
            
            for link in job_links:
                yield scrapy.Request(
                    link,
                    meta=   {
                            'playwright': True,
                            'playwright_include_page': True,
                            'playwright_page_methods': [
                            # Wait until the document is fully loaded
                            {"name": "wait_for_load_state", "args": ["domcontentloaded"]},
                            # Optional: add a timeout (in milliseconds) for the page to load
                            {"name": "set_default_navigation_timeout", "args": [30000]}  # 30 seconds
                        ], 
                        'playwright_context_kwargs': {
                            # 'user_agent': random.choice(USER_AGENTS),
                            'user_agent': USER_AGENTS[3],

                        }
                            },
                    callback=self.parse_job_detail,
                    errback=self.errback_close_page,
                )
            next_page = current_page + 1
            params = {
                "q": self.query,  # ex: "sécurité informatique"
                "l": self.country,  # ex: "France"
                "job_type[]": ["Stage", "STAGE"],
                "p": next_page,
               }   
            next_link = f"{self.base_url}?{urlencode(params, doseq=True)}"
            if DEBUG_NEXT_LINKS : 
                with open("next_link.txt", "a") as f:
                  f.write(next_link +"\n")
            if next_link and current_page < DEPTH_LIMIT:
                yield scrapy.Request(
                    rendered.urljoin(next_link),
                    meta={
                        'playwright': True,
                        'playwright_include_page': True,
                        'page': response.meta.get('page', 1) + 1,
                        'playwright_context_kwargs': {
                            # 'user_agent': random.choice(USER_AGENTS),
                            'user_agent': USER_AGENTS[3],

                        }
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
            await page.wait_for_selector('div.details-header', timeout=15000)

            content = await page.content()
            if DEBUG : 
                with open(f"debug_.html", "w", encoding="utf-8") as f:
                   f.write(content)

            rendered = HtmlResponse(url=response.url, body=content, encoding='utf-8')

            metadata_block = rendered.css('div.details-header')

            # --- Job title ---
            title = metadata_block.css('h1.details-header__title::text').get('').strip()

            # --- Company name & URL ---
            
            company_name = metadata_block.css('li.listing-item__info--item.listing-item__info--item-company::text').get(default='').strip()
            company_url = rendered.css('a.btn__profile::attr(href)').get()
        
            # scrapping company profile page
            # --- Company logo ---
            company_logo = metadata_block.css('img[alt]::attr(src)').get('')
            # --- Location ---
            location = metadata_block.css('li.listing-item__info--item.listing-item__info--item-location a::text').get('').strip()
            # --- Apply URL ---
            apply_url = rendered.css('a.details-footer__btn-apply::attr(href)').get('')


            # --- Date posted ---
            #date_posted_raw = metadata_block.css('time::attr(datetime)').get('')
            date_posted = metadata_block.css('li.listing-item__info--item.listing-item__info--item-date::text').get(default='').strip()
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
            description_text = "".join(response.css('div.details-body__content.content-text ::text').getall()).strip()
    
          
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
                "apply_url": apply_url,
                "location": location,
                "date_posted": str(date_posted) if date_posted else None,
                "description": description_text,
              
            }

            self.logger.info(f"Scraped job: {title} @ {company_name}")
            #yield job_post_data for testing before building JobPost
            # Yield as JobPost if your model supports it, otherwise yield dict
            try:
                # location_obj = None
                # if location:
                #     location_obj = Location(city=location,country=Country.FRANCE)

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
                    is_remote= None ,
                    listing_type= None,
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
                    work_from_home_type= None,
                    company_industry=None,
                    salary=None,
                    starting_date=None,
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
                    f.write(company_url + "\n" )
            if company_url:
                yield scrapy.Request(
                    company_url,
                    meta={
                        'playwright': True,
                        'playwright_include_page': True,
                        'job_post': copy.deepcopy(job_post),
                        'playwright_context_kwargs': {
                            # 'user_agent': random.choice(USER_AGENTS),
                            'user_agent': USER_AGENTS[3],

                        }
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
                'li.listing-item__info--item.listing-item__info--item-website a::attr(href)'
            ).get('').strip()

        
            # Use Playwright for more reliable block extraction
            company_description = "\n\n".join(
                response.css('div.profile__info__description  *::text').getall()
            )
            if DEBUG_DESCRIPTION :
                with open(f"description_company.txt", "a", encoding="utf-8") as f:
                    f.write(company_description)

            self.logger.info(
                f"Company page scraped: {response.url} | "
                f"Website: {company_website} | "
            )

            # --- Enrich the job_post with company data ---
            job_post["company_url_direct"] = company_website or job_post.get("company_url_direct")
            job_post["company_description"] = company_description

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