import copy
import scrapy
from scrapy.http import HtmlResponse
from urllib.parse import urlencode
from model import JobPost

DEPTH = 10
DEBUG = False
class WelcomeToTheJungleSpider(scrapy.Spider):
    name = "welcometothejungle"
    allowed_domains = ["welcometothejungle.com"]
    
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
        "MONGO_DATABASE": "jobs_welcometothejungle", 
    }
    
    def __init__(self, query: str = "", country: str = "FR", contract_type: str = "internship", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.query = query
        self.country = country
        self.contract_type = "internship"
        self.base_url = "https://www.welcometothejungle.com/fr/jobs"
        self.job_log_file = "job_link_mapping.txt"

    def start_requests(self):
        params = {
            "refinementList[offices.country_code][]": self.country,
            "refinementList[contract_type][]": self.contract_type,
            "query": self.query,
            "page": 1,
        }
        url = f"{self.base_url}?{urlencode(params, doseq=True)}"
        if DEBUG : 
            with open("url.txt", "w") as f:
                f.write(url)
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
            await page.wait_for_selector('a[role="link"][href*="/jobs/"]', timeout=20000)

            content = await page.content()
            rendered = HtmlResponse(url=response.url, body=content, encoding='utf-8')

            job_links = rendered.xpath(
                '//a[@role="link" and contains(@href, "/jobs/")]/@href'
            ).getall()
            job_links = list(set(job_links))  # Remove duplicates
            import time
            #time.sleep(10)  # Add a small delay to be polite to the server
            if not job_links:
                self.logger.info("No job links found. Stopping.")
                return
            if DEBUG : 
                with open("job_links.txt", "a") as f:
                    f.write("\n".join(job_links))
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
                    f.write(next_link)
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
                await page.wait_for_selector('[data-testid="job-metadata-block"]', timeout=20000)
            except Exception:
                self.logger.warning(f"job-metadata-block not found at {response.url}")
                if DEBUG : 
                    with open("failed_metadatablocks.html", "a", encoding="utf-8") as f:
                        f.write(f"job-metadata-block not found at {response.url}\n")
                return

            content = await page.content()
            # if DEBUG : 
            # with open(f"debug_{filename}.html", "w", encoding="utf-8") as f:
            #     f.write(content)

            rendered = HtmlResponse(url=response.url, body=content, encoding='utf-8')

            metadata_block = rendered.css('[data-testid="job-metadata-block"]')

            # --- Job title ---
            title = metadata_block.css('h2::text').get('').strip()

            # --- Company name & URL ---
            company_name = metadata_block.css('a[href*="/companies/"] span::text').get('').strip()
            company_relative_url = metadata_block.css('a[href*="/companies/"]::attr(href)').get('')
            company_url = f"https://www.welcometothejungle.com{company_relative_url}" if company_relative_url else None
            # scrapping company profile page
            
            # --- Company logo ---
            company_logo = metadata_block.css('img[alt]::attr(src)').get('')

            # --- Metadata tags (contract, location, remote, salary) ---
            tags = metadata_block.css('div.sc-fibHhp')

            contract_type = None
            contract_duration = None
            location = None
            remote_type = None
            salary = None

            for tag in tags:
                svg_alt = tag.css('svg::attr(alt)').get('')
                
                if svg_alt == 'Contract':
                    contract_type = tag.css('::text').getall()
                    contract_type = ' '.join(t.strip() for t in contract_type if t.strip())
                    # Extract duration if present e.g. "(6 mois)"
                    duration_text = tag.css('span::text').get('')
                    if duration_text:
                        contract_duration = duration_text.strip('()')

                elif svg_alt == 'Location':
                    location = tag.css('span span::text').get('').strip()

                elif svg_alt == 'Remote':
                    remote_texts = tag.css('span::text').getall()
                    remote_type = ' '.join(t.strip() for t in remote_texts if t.strip())

                elif svg_alt == 'Salary':
                    salary_parts = tag.css('::text').getall()
                    salary = ' '.join(t.strip() for t in salary_parts if t.strip())

            # --- Apply URL ---
            apply_url = metadata_block.css(
                'a[data-testid="job_header-button-apply"]::attr(href)'
            ).get('')

            # --- Date posted ---
            date_posted_raw = metadata_block.css('time::attr(datetime)').get('')
            date_posted = None
            if date_posted_raw:
                try:
                    from datetime import datetime
                    date_posted = datetime.fromisoformat(
                        date_posted_raw.replace("Z", "+00:00")
                    ).date()
                except Exception:
                    pass

            # --- Job description ---
            description_html = " ".join(rendered.css('[data-testid="job-section-description"] [data-is-text-too-long] ::text').getall()).strip()
            # description_html = await page.evaluate('''() => {
            #     const el = document.querySelector('[data-testid="job-section-description"] [data-is-text-too-long]');
            #     return el ? el.innerHTML : "";
            # }''')

            # --- Profile / experience required ---
            profile_html = "".join(rendered.css('[data-testid="job-section-experience"] [data-is-text-too-long] ::text').getall()).strip()
            # profile_html = await page.evaluate('''() => {
            #     const el = document.querySelector('[data-testid="job-section-experience"] [data-is-text-too-long]');
            #     return el ? el.innerHTML : "";
            # }''')
                        # Build result dict (adapt to your JobPost model as needed)
            job_post_data = {
                "origine": "welcometothejungle",
                "title": title,
                "company_name": company_name,
                "company_url": company_url,
                "company_logo": company_logo,
                "job_url": response.url,
                "apply_url": apply_url,
                "location": location,
                "contract_type": contract_type,
                "contract_duration": contract_duration,
                "remote_type": remote_type,
                "salary": salary,
                "date_posted": str(date_posted) if date_posted else None,
                "description": description_html,
                "profile": profile_html,
            }

            self.logger.info(f"Scraped job: {title} @ {company_name}")

            # Yield as JobPost if your model supports it, otherwise yield dict
            try:
                

                job_post = JobPost(
                    origine="welcometothejungle",
                    id=None,
                    title=title,
                    company_name=company_name,
                    job_url=response.url,
                    job_url_direct=apply_url,
                    location=location,
                    description=description_html,
                    company_url=company_url,
                    company_url_direct=company_url,
                    compensation=None,
                    date_posted= str(date_posted) if date_posted else None,
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
                    profile=profile_html,
                    credibility_score = None,
                    label = None,
                    credibility_flags = None,
                    s1_score          = None,
                    s1_details        = None,
                    s4_score          = None,
                    s4_details        = None,
                    s3_score          = None,
                    s3_details        = None,
                    scored_at         = None,
                    score             = None,
                )
                #yield job_post
            except Exception as e:
                self.logger.error(f"JobPost build error: {e}")
                yield job_post_data

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
            else:
                yield job_post
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

            try:
                await page.wait_for_selector(
                    '[data-testid="organization-page-profile-sidebar"]',
                    timeout=15000
                )
            except Exception:
                self.logger.warning(f"Company sidebar not found at {response.url}")
                yield job_post
                return

            content = await page.content()
            rendered = HtmlResponse(url=response.url, body=content, encoding='utf-8')

            # --- Company website ---
            company_website = rendered.css(
                '[data-testid="showcase-header-website-link"]::attr(href)'
            ).get('').strip()

            # --- Company sector ---
            company_sector = rendered.css(
                '[data-testid="showcase-header-sector"]::text'
            ).get('').strip()

            # --- Company location ---
            company_location = rendered.css(
                '[data-testid="showcase-header-office"]::text'
            ).get('').strip()

            # --- Social media links ---
            social_links = {}
            sidebar = rendered.css('[data-testid="organization-page-profile-sidebar"]')
            
            social_networks = {
                'linkedin': '[data-testid="social-network-linkedin"]::attr(href)',
                'twitter': '[data-testid="social-network-twitter"]::attr(href)',
                'facebook': '[data-testid="social-network-facebook"]::attr(href)',
                'instagram': '[data-testid="social-network-instagram"]::attr(href)',
                'youtube': '[data-testid="social-network-youtube"]::attr(href)',
            }
            for network, selector in social_networks.items():
                url = sidebar.css(selector).get('').strip()
                if url:
                    social_links[network] = url

            # --- Company presentation blocks ---
            # Each block has a h2 title + div content
            presentation_blocks = {}
            blocks = sidebar.css('[data-testid="organization-content-block-text"]')
            
            for block in blocks:
                block_title = block.css('h2::text').get('').strip()
                block_content = block.css('.sc-cyYRJy').get('')
                
                # Fallback: get inner text if class is hashed
                if not block_content:
                    block_content = block.evaluate('''el => {
                        const div = el.querySelector('article > div');
                        return div ? div.innerHTML : "";
                    }''') if hasattr(block, 'evaluate') else ''
                
                if block_title and block_content:
                    presentation_blocks[block_title] = block_content

            # Use Playwright for more reliable block extraction
            # blocks_data = await page.evaluate('''() => {
            #     const blocks = document.querySelectorAll(
            #         '[data-testid="organization-content-block-text"]'
            #     );
            #     const result = {};
            #     blocks.forEach(block => {
            #         const title = block.querySelector('h2');
            #         const content = block.querySelector('article > div');
            #         if (title && content) {
            #             result[title.innerText.trim()] = content.innerHTML;
            #         }
            #     });
            #     return result;
            # }''')
            blocks_data = {}

            for block in response.css('[data-testid="organization-content-block-text"]'):
                # Get the title text
                title = block.css('h2::text').get()
                if title:
                    title = title.strip()
                
                # Get the content HTML inside <article> > <div>
                content = block.css('article > div ::text').getall()  # .get() returns HTML including inner tags
                content = ' '.join(content).strip()

                if title and content:
                    blocks_data[title] = content

            # Social links via Playwright for reliability
            social_links_js = await page.evaluate('''() => {
                const networks = ['linkedin', 'twitter', 'facebook', 
                                'instagram', 'youtube', 'tiktok'];
                const result = {};
                networks.forEach(network => {
                    const el = document.querySelector(
                        `[data-testid="social-network-${network}"]`
                    );
                    if (el) result[network] = el.getAttribute('href');
                });
                return result;
            }''')

            self.logger.info(
                f"Company page scraped: {response.url} | "
                f"Website: {company_website} | "
                f"Sector: {company_sector} | "
                f"Location: {company_location} | "
                f"Social: {social_links_js} | "
                f"Blocks: {list(blocks_data.keys())}"
            )

            # --- Enrich the job_post with company data ---
            job_post["company_url_direct"] = company_website or job_post.get("company_url_direct")
            job_post["company_industry"] = company_sector or job_post.get("company_industry")
            job_post["company_addresses"] = company_location or job_post.get("company_addresses")
            job_post["company_social_links"] = social_links_js or job_post.get("company_social_links")
            job_post["company_description"] = blocks_data.get(
                'Présentation', 
                job_post.get("company_description")
            )

            # Store additional data in a custom field if your model supports it
            # Otherwise log it
            self.logger.info(f"Extra blocks: {list(blocks_data.keys())}")
            self.logger.info(f"Social links: {social_links_js}")
            job_title = getattr(job_post, "title", "UNKNOWN") or "UNKNOWN"
            status = "SUCCESS"

            # Log the job
            if DEBUG : 
                with open(self.job_log_file, "a", encoding="utf-8") as f:
                    f.write(f"{job_post.job_url} -> {job_title} -> {status}\n")

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