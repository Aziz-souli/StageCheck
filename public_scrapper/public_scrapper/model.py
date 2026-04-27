from enum import Enum
from pydantic import BaseModel
from typing import Optional
from datetime import date
import scrapy
class Country(Enum):
    """
    Gets the subdomain for Indeed and Glassdoor.
    The second item in the tuple is the subdomain (and API country code if there's a ':' separator) for Indeed
    The third item in the tuple is the subdomain (and tld if there's a ':' separator) for Glassdoor
    """

    FRANCE = ("france", "fr", "fr")

    @property
    def indeed_domain_value(self):
        subdomain, _, api_country_code = self.value[1].partition(":")
        if subdomain and api_country_code:
            return subdomain, api_country_code.upper()
        return self.value[1], self.value[1].upper()
    
class Compensation(BaseModel):
    interval: None
    min_amount: float | None = None
    max_amount: float | None = None
    currency: Optional[str] = "EUR"

class Location(BaseModel):
    country: Country | str | None = None
    city: Optional[str] = None
    state: Optional[str] = None

    def display_location(self) -> str:
        location_parts = []
        if self.city:
            location_parts.append(self.city)
        if self.state:
            location_parts.append(self.state)
        if isinstance(self.country, str):
            location_parts.append(self.country)
        elif self.country and self.country not in (
            Country.US_CANADA,
            Country.WORLDWIDE,
        ):
            country_name = self.country.value[0]
            if "," in country_name:
                country_name = country_name.split(",")[0]
            if country_name in ("usa", "uk"):
                location_parts.append(country_name.upper())
            else:
                location_parts.append(country_name.title())
        return ", ".join(location_parts)

class JobPost(scrapy.Item):
            origine = scrapy.Field()
            id = scrapy.Field()
            title = scrapy.Field()
            company_name = scrapy.Field()
            job_url = scrapy.Field()
            job_url_direct = scrapy.Field()
            location = scrapy.Field()
            starting_date = scrapy.Field()
            description = scrapy.Field()
            company_url = scrapy.Field()
            company_url_direct = scrapy.Field()

            compensation = scrapy.Field()
            date_posted = scrapy.Field()
            emails = scrapy.Field()
            is_remote = scrapy.Field()
            listing_type = scrapy.Field()

            # LinkedIn specific
            job_level = scrapy.Field()

            # LinkedIn and Indeed specific
            company_industry = scrapy.Field()

            # Indeed specific
            company_addresses = scrapy.Field()
            company_num_employees = scrapy.Field()
            company_revenue = scrapy.Field()
            company_description = scrapy.Field()
            company_logo = scrapy.Field()
            banner_photo_url = scrapy.Field()

            # LinkedIn only
            job_function = scrapy.Field()

            # Naukri specific
            skills = scrapy.Field()
            experience_range = scrapy.Field()
            company_rating = scrapy.Field()
            company_reviews_count = scrapy.Field()
            vacancy_count = scrapy.Field()
            work_from_home_type = scrapy.Field()
            profile = scrapy.Field()
            company_social_links = scrapy.Field()
            company_slogans = scrapy.Field()    
            company_followers = scrapy.Field()
            company_type = scrapy.Field()
            salary = scrapy.Field()
            credibility_score = scrapy.Field()

            # Scoring fields — added here so Scrapy Item accepts them
            score = scrapy.Field()
            label = scrapy.Field()
            credibility_flags = scrapy.Field()
            s1_score          = scrapy.Field()
            s1_details        = scrapy.Field()
            s4_score          = scrapy.Field()
            s4_details        = scrapy.Field()
            s3_score          = scrapy.Field()
            s3_details        = scrapy.Field()
            scored_at         = scrapy.Field()
            score             = scrapy.Field()