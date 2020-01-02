import re
from pupa.scrape import Person, Scraper
from openstates.utils import LXMLMixin, validate_phone_number


class AKPersonScraper(Scraper, LXMLMixin):
    jurisdiction = "ak"
    latest_only = True

    def _scrape_person(self, url):
        doc = self.lxmlize(url)
        content = doc.xpath('//div[@class="tab-content"]')[0]

        photo_url = content.xpath('div[@class="bioleft"]/img/@src')[0]
        name = content.xpath('div[@class="bioright"]/span/text()')[0]
        leg_type, _, name = name.strip().partition(" ")
        chamber = "upper" if leg_type == "Senator" else "lower"

        email = content.xpath('div[@class="bioright"]//a/@href')
        if email:
            email = email[0].replace("mailto:", "").strip()
        else:
            self.warning("no email for " + name)

        bioright = content.xpath('div[@class="bioright"]')[0].text_content()
        district, party = re.search(
            r"District: (\S+).*Party: ([a-zA-Z ]+)", bioright, re.DOTALL
        ).groups()
        person = Person(
            primary_org=chamber,
            district=district,
            name=name,
            party=self._party_map[party.strip()],
            image=photo_url,
        )
        person.add_source(url)
        person.add_link(url)

        capitol_office = (
            doc.xpath('//strong[text()="Session Contact"]')[0]
            .getparent()
            .text_content()
            .strip()
            .splitlines()
        )
        capitol_office = [line.strip() for line in capitol_office]

        assert capitol_office[0] == "Session Contact"
        person.add_contact_detail(
            type="address",
            value=capitol_office[1] + "\n" + capitol_office[2],
            note="Capitol Office",
        )

        assert capitol_office[3].startswith("Phone:")
        capitol_phone = capitol_office[3][len("Phone: ") :].strip()
        if capitol_phone and validate_phone_number(capitol_phone):
            if len(capitol_phone) == 8:  # missing area code
                capitol_phone = "907-" + capitol_phone
            person.add_contact_detail(
                type="voice", value=capitol_phone, note="Capitol Office Phone"
            )

        # Some legislators lack a `Fax` line
        if len(capitol_office) >= 5:
            assert capitol_office[4].startswith("Fax:")
            fax = capitol_office[4][len("Fax: ") :].strip()
            if fax and validate_phone_number(fax):
                person.add_contact_detail(
                    type="fax", value=fax, note="Capitol Office Fax"
                )

        person.add_contact_detail(type="email", value=email, note="E-mail")

        interim_office = doc.xpath('//strong[text()="Interim Contact"]')
        if interim_office:
            interim_office = (
                interim_office[0].getparent().text_content().strip().splitlines()
            )
            interim_office = [line.strip() for line in interim_office]

            assert interim_office[0] == "Interim Contact"
            person.add_contact_detail(
                type="address",
                note="District Office",
                value=interim_office[1] + "\n" + interim_office[2],
            )

            assert interim_office[3].startswith("Phone:")
            district_phone = interim_office[3][len("Phone:") :]
            if district_phone and validate_phone_number(district_phone):
                person.add_contact_detail(
                    type="voice", value=district_phone, note="District Office Phone"
                )

            if len(interim_office) >= 5:
                assert interim_office[4].startswith("Fax:")
                district_fax = interim_office[4][len("Fax:") :]
                if district_fax and validate_phone_number(district_fax):
                    person.add_contact_detail(
                        type="fax",
                        value=interim_office[4][len("Fax: ") :],
                        note="District Office Fax",
                    )
        yield person

    def scrape_chamber(self, session, chamber=None):
        self._party_map = {
            "Democrat": "Democratic",
            "Republican": "Republican",
            "Non Affiliated": "Independent",
            "Not Affiliated": "Independent",
        }

        member_types = {"upper": "Senator", "lower": "Representative"}

        url = "http://www.akleg.gov/basis/mbr_info.asp?session={}".format(session)

        page = self.lxmlize(url)

        items = page.xpath('//table[@id="members"]/tr')[1:]

        for item in items:
            link = item.xpath("td//a")[0]
            if chamber and not link.text.startswith(member_types[chamber]):
                continue

            leg_url = link.attrib["href"]
            yield self._scrape_person(leg_url)

    def scrape(self, chamber=None):
        session = 31  # TODO: where does this come from?
        if chamber:
            yield from self.scrape_chamber(session, chamber=chamber)
        else:
            yield from self.scrape_chamber(session)
