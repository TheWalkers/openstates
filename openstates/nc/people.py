import re
from pupa.scrape import Scraper, Person
import lxml.html


class NCPersonScraper(Scraper):
    def scrape(self, chamber=None):
        if chamber:
            yield from self.scrape_chamber(chamber)
        else:
            yield from self.scrape_chamber("upper")
            yield from self.scrape_chamber("lower")

    def scrape_chamber(self, chamber):
        chamber_letter = dict(lower="H", upper="S")[chamber]
        url = "https://www.ncleg.gov/Members/MemberTable/{}".format(chamber_letter)

        data = self.get(url).text
        doc = lxml.html.fromstring(data)
        doc.make_links_absolute("https://www.ncleg.gov")
        rows = doc.xpath('//table[@id="memberTable"]/tbody/tr')
        self.warning("rows found: {}".format(len(rows)))

        for row in rows:
            party, district, _, _, full_name, counties = row.getchildren()

            if "Resigned" in full_name.text_content():
                continue

            party = party.text_content().strip()
            party = dict(D="Democratic", R="Republican")[party]

            district = district.text_content().strip()

            link = full_name.xpath("a/@href")[0]
            full_name = full_name.xpath("a")[0].text_content()
            full_name = full_name.replace(u"\u00a0", " ")

            # scrape legislator page details
            lhtml = self.get(link).text
            ldoc = lxml.html.fromstring(lhtml)
            ldoc.make_links_absolute("https://www.ncleg.gov")
            cols = ldoc.xpath('//div[contains(@class, "card-body")]/div/div')

            address = capitol_address = phone = capitol_phone = email = None

            # column 0 has a link to the member photo
            photo_url = cols[0].xpath("figure/a/@href")[0]

            # column 1 has addresses
            addr_ps = cols[1].xpath(
                '//h6[contains(text(), "Mailing Address:")]/following-sibling::p'
            )
            if addr_ps and addr_ps[0].text != "None":
                addr = "\n".join([p.text.strip() for p in addr_ps])
                if chamber == "upper":
                    capitol_address = addr
                else:
                    address = addr

            addr_ps = cols[1].xpath(
                '//h6[contains(text(), "Legislative Office:")]/following-sibling::p'
            )
            if addr_ps and addr_ps[0].text != "None":
                capitol_address = "\n".join([p.text.strip() for p in addr_ps[:2]])
                if addr_ps[2:]:
                    cap_phone_a = addr_ps[2].xpath('//a[starts-with(@href, "tel:")]')
                    if cap_phone_a:
                        capitol_phone = cap_phone_a[0].text

            # column 2 has phone and email
            phone_a = cols[2].xpath(
                '//p[contains(text(), "Phone:")]/ancestor::div/following-sibling::div/p/a[starts-with(@href, "tel:")]'
            )
            if phone_a:
                phone = phone_a[0].text.strip()

            if phone and not capitol_phone:
                capitol_phone, phone = phone, None

            email_a = cols[2].xpath(
                '//p[contains(text(), "Email:")]/ancestor::div/following-sibling::div/p/a[starts-with(@href, "mailto:")]'
            )
            if email_a:
                capitol_email = email_a[0].text.strip()

            # column 3 has district map, skipped

            # save legislator
            person = Person(
                name=full_name,
                district=district,
                party=party,
                primary_org=chamber,
                image=photo_url,
            )
            person.extras["counties"] = [
                c.strip() for c in counties.text_content().split(",")
            ]
            person.add_link(link)
            person.add_source(link)

            if address:
                person.add_contact_detail(
                    type="address", value=address, note="District Office"
                )
            if capitol_address:
                person.add_contact_detail(
                    type="address", value=capitol_address, note="Capitol Office"
                )

            if phone:
                person.add_contact_detail(
                    type="voice", value=phone, note="District Office"
                )
            if capitol_phone:
                person.add_contact_detail(
                    type="voice", value=capitol_phone, note="Capitol Office"
                )

            if capitol_email:
                person.add_contact_detail(
                    type="email", value=capitol_email, note="Capitol Office"
                )
            yield person
