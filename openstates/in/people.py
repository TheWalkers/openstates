import binascii
import lxml.html

from pupa.scrape import Person, Scraper
from .apiclient import ApiClient
from .utils import get_with_increasing_timeout
import scrapelib


def decode_email(s):
    # hex values of chars xored with first byte
    bs = binascii.unhexlify(s)
    return ''.join([chr(b ^ bs[0]) for b in bs[1:]])


class INPersonScraper(Scraper):
    jurisdiction = 'in'

    def scrape(self, chamber=None):
        if chamber:
            yield from self.scrape_chamber(chamber)
        else:
            yield from self.scrape_chamber('upper')
            yield from self.scrape_chamber('lower')

    def scrape_chamber(self, chamber):
        client = ApiClient(self)
        session = self.latest_session()
        base_url = "http://iga.in.gov/legislative"
        api_base_url = "https://api.iga.in.gov"
        chamber_name = "senate" if chamber == "upper" else "house"
        r = client.get("chamber_legislators", session=session, chamber=chamber_name)
        all_pages = client.unpaginate(r)
        for leg in all_pages:
            firstname = leg["firstName"]
            lastname = leg["lastName"]
            party = leg["party"]
            link = leg["link"]
            api_link = api_base_url+link
            html_link = base_url+link.replace("legislators/", "legislators/legislator_")
            try:
                html = get_with_increasing_timeout(self, html_link, fail=True,
                                                   kwargs={"verify": False})
            except scrapelib.HTTPError:
                self.logger.warning("Legislator's page is not available.")
                continue

            doc = lxml.html.fromstring(html.text)
            doc.make_links_absolute(html_link)
            address, phone = doc.xpath("//address")
            address = address.text_content().strip()
            address = "\n".join([l.strip() for l in address.split("\n")])
            phone = phone.text_content().strip()
            try:
                district = doc.xpath("//span[@class='district-heading']"
                                     )[0].text.lower().replace("district", "").strip()
            except IndexError:
                self.warning("skipping legislator w/o district")
                continue

            email = None
            email_link = doc.xpath('//a[contains(@href, "/cdn-cgi/l/email-protection#")]/@href')
            if email_link:
                _, encoded = email_link[0].rsplit("#", 1)
                email = decode_email(encoded)

            image_link = base_url+link.replace("legislators/", "portraits/legislator_")
            legislator = Person(primary_org=chamber,
                                district=district,
                                name=" ".join([firstname, lastname]),
                                party=party,
                                image=image_link)
            legislator.add_contact_detail(type="address", note="Capitol Office", value=address)
            legislator.add_contact_detail(type="voice", note="Capitol Office", value=phone)
            if email:
                legislator.add_contact_detail(type="email", note="Capitol Office", value=email)
            legislator.add_link(html_link)
            legislator.add_source(html_link)
            legislator.add_source(api_link)

            yield legislator
