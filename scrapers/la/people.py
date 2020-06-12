import re

from openstates.scrape import Person, Scraper
from utils import LXMLMixin


class LAPersonScraper(Scraper, LXMLMixin):
    def scrape(self, chamber=None):
        chambers = [chamber] if chamber is not None else ["upper", "lower"]
        for chamber in chambers:
            yield from getattr(self, "scrape_" + chamber)(chamber)

    def scrape_upper_leg_page(self, url, who):
        page = self.lxmlize(url)

        (who,) = [
            x
            for x in page.xpath("//tr/td/font/text()")
            if x.strip().startswith("Senator ") or x.strip().startswith("President ")
        ]
        who = re.search(r"(?u)^\s*(?:Senator|President Pro Tempore)\s*(.*?)\s*$", who).group(1)

        if "Vacant" in who:
            return

        (district,) = [
            x
            for x in page.xpath("//tr/td/font/text()")
            if x.strip().startswith("District - ")
        ]
        district = re.search(r"(?u)^\s*District\s*-\s*(.*?)\s*$", district).group(1)

        info = [
            x.strip()
            for x in page.xpath(
                '//font[contains(text(), "Information:")]/' "ancestor::table[1]//text()"
            )
            if x.strip()
        ]

        parties = {"Republican": "Republican", "Democrat": "Democratic"}
        party_index = info.index("Party:") + 1
        party = parties[info[party_index]]

        phone_index = info.index("District Phone") + 1
        phone = info[phone_index]
        phone_digits = sum(c.isdigit() for c in phone)
        if phone_digits != 10:
            self.warning("Phone number is invalid: {}".format(phone))
            phone = ""

        # Address exists for all lines between party and phone
        address = "\n".join(info[party_index + 2 : phone_index - 1])
        address = address.replace("\r", "")

        if not address:
            address = "No Address Found"

        fax_index = info.index("Fax") + 1
        fax = info[fax_index]
        fax_digits = sum(c.isdigit() for c in fax)
        if fax_digits != 10:
            self.warning("fax number is invalid: {}".format(fax))
            fax = ""

        email_index = info.index("E-mail Address") + 1
        email = info[email_index]
        if "@" not in email:
            self.warning("Email info is not valid: {}".format(email))
            email = ""

        person = Person(name=who, district=district, party=party, primary_org="upper")

        contacts = [
            (address, "address"),
            (phone, "voice"),
            (email, "email"),
            (fax, "fax"),
        ]

        for value, key in contacts:
            if value:
                person.add_contact_detail(type=key, value=value, note="District Office")

        person.add_source(url)
        person.add_link(url)

        yield person

    def scrape_upper(self, chamber):
        url = "http://senate.la.gov/Senators/"
        page = self.lxmlize(url)
        table = page.xpath("//table[@width='96%']")[0]
        legs = table.xpath(".//tr//a[contains(@href, 'senate.la.gov')]")
        for leg in legs:
            who = leg.text_content().strip()
            if who == "":
                continue
            yield from self.scrape_upper_leg_page(leg.attrib["href"], who)

    def scrape_lower_legislator(self, url, leg_info):
        page = self.lxmlize(url)

        name = page.xpath('//span[@id="body_FormView5_FULLNAMELabel"]/text()')[
            0
        ].strip()
        if name.startswith("District ") or name.startswith("Vacant "):
            self.warning("Seat is vacant: {}".format(name))
            return

        if name.endswith(", I"):
            name = name[:-3]

        photo = page.xpath('//img[contains(@src, "/h_reps/RepPics")]')[0].attrib["src"]
        party_flags = {
            "Democrat": "Democratic",
            "Republican": "Republican",
            "Independent": "Independent",
        }
        party_info = page.xpath(
            '//span[@id="body_FormView5_PARTYAFFILIATIONLabel"]/text()'
        )

        try:
            party = party_flags[party_info[0].strip()]
        except KeyError:
            if name == 'James H. "Jim" Morris':
                party = "Republican"
            else:
                raise

        try:
            email = page.xpath(
                '//span[@id="body_FormView6_EMAILADDRESSPUBLICLabel"]/text()'
            )[0].strip()
        except IndexError:
            email = None
        district = leg_info["dist"].replace("Dist", "").strip()

        person = Person(
            name=name, party=party, district=district, primary_org="lower", image=photo
        )

        # whee, special case
        if leg_info["phone"] == "504-83POLLY (837-6559)":
            leg_info["phone"] = "504-837-6559"

        # fix a typo
        if leg_info["phone"].startswith("9225) "):
            print("PHONE %r" % leg_info["phone"])
            leg_info["phone"] = "(225) " + leg_info["phone"][6:]

        contacts = [
            (leg_info["office"], "address"),
            (leg_info["phone"], "voice"),
            (email, "email"),
        ]

        for value, key in contacts:
            if value:
                person.add_contact_detail(type=key, value=value, note="District Office")

        person.add_source(url)
        person.add_link(url)

        yield person

    def scrape_lower(self, chamber):
        url = "http://house.louisiana.gov/H_Reps/H_Reps_FullInfo.aspx"
        page = self.lxmlize(url)
        meta = ["name", "dist", "office", "phone"]
        for tr in page.xpath(
            "//table[@id='body_ListView1_itemPlaceholderContainer']//tr"
        )[1:]:
            ths = tr.xpath("./th")
            if ths == []:
                continue

            info = {}
            for i in range(0, len(meta)):
                info[meta[i]] = ths[i].text_content().strip()

            hrp = tr.xpath(".//a[contains(@href, 'H_Reps')]")[0].attrib["href"]

            yield from self.scrape_lower_legislator(hrp, info)
