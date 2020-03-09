import re
import lxml.html

from pupa.scrape import Person, Scraper


def _get_table_item(doc, name):
    """ fetch items out of table that has a left column of th """
    return doc.xpath('//dt[contains(text(), "%s")]/following-sibling::dd' % name)[0]


class MDPersonScraper(Scraper):
    urls = {
        "lower": "http://mgaleg.maryland.gov/mgawebsite/Members/Index/house",
        "upper": "http://mgaleg.maryland.gov/mgawebsite/Members/Index/senate",
    }

    def scrape(self, chamber=None):
        chambers = [chamber] if chamber is not None else ["upper", "lower"]
        if "upper" in chambers:
            yield from self.scrape_table("upper")
        if "lower" in chambers:
            yield from self.scrape_table("lower")

    def scrape_table(self, chamber):
        url = self.urls[chamber]
        html = self.get(url).text
        doc = lxml.html.fromstring(html)
        doc.make_links_absolute(url)

        seen = set()

        for row in doc.xpath('//div[contains(@class, "member-index-cell")]/div/div'):

            img_cell, text_cell = row.getchildren()

            if "to be announced" in text_cell.text_content().lower():
                continue

            leg_a = text_cell.xpath('.//a')[0]
            leg_url = leg_a.attrib['href']
            name = leg_a.text

            district = re.search(
                r"District (\d{1,2}[ABCD]?)",
                text_cell.text_content()
            ).group(1)

            key = name + district
            if key in seen:  # leadership listed twice, skip the 2nd
                continue
            seen.add(key)

            photo_url = img_cell.xpath("a/img/@src")[0]

            # get details
            html = self.get(leg_url).text
            ldoc = lxml.html.fromstring(html)
            ldoc.make_links_absolute(leg_url)

            party = _get_table_item(ldoc, "Party").text
            if party == "Democrat":
                party = "Democratic"
            capitol_info = _get_table_item(ldoc, "Annapolis Info")
            addr_lines, phone_lines = capitol_info.xpath("dl/dd")

            address = [s.strip() for s in addr_lines.text_content().split('\n') if s.strip()]
            address = "\n".join(address)

            phone = None
            fax = None
            for line in phone_lines.text_content().split('\n'):
                if "Phone" in line:
                    phone = re.findall(r"Phone (\d{3}-\d{3}-\d{4})", line)[0]
                elif "Fax" in line:
                    # Number oddities: one has two dashes, one has a dash and then a space.
                    line = line.replace("--", "-").replace("- ", "-")
                    fax = re.findall(r"Fax (\d{3}-\d{3}-\d{4})", line)[0]

            email_path = ldoc.xpath('//a[contains(@href, "mailto:")]/@href')
            emails = set()
            for path in email_path:
                emails.add(re.match(r"mailto:([^?]+)", path).group(1))
            if not emails:
                email = None
            elif len(emails) == 1:
                email = emails.pop()
            else:
                raise AssertionError("Multiple email links found on page")

            img_src = ldoc.xpath('//img[@class="sponimg"]/@src')
            if img_src:
                photo_url = img_src[0]

            names = name.split(", ")
            name = " ".join([names[1], names[0]] + names[2:])

            leg = Person(
                primary_org=chamber,
                district=district,
                name=name,
                party=party,
                image=photo_url,
            )
            leg.add_source(url=leg_url)
            leg.add_link(url=leg_url)

            if address:
                leg.add_contact_detail(
                    type="address", value=address, note="Capitol Office"
                )
            if phone:
                leg.add_contact_detail(type="voice", value=phone, note="Capitol Office")
            if fax:
                leg.add_contact_detail(type="fax", value=fax, note="Capitol Office")
            if email:
                leg.add_contact_detail(type="email", value=email, note="Capitol Office")

            yield leg
