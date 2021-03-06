import re
import datetime
from itertools import chain

from openstates.scrape import Person, Scraper
from utils import LXMLMixin, validate_phone_number
from openstates.utils import convert_pdf


class NYPersonScraper(Scraper, LXMLMixin):
    def _split_list_on_tag(self, elements, tag):
        data = []
        for element in elements:
            element_class = None

            try:
                element_class = element.attrib["class"]
            except KeyError:
                pass

            if element_class == tag:
                yield data
                data = []
            else:
                data.append(element)

    def _scrape_from_pdf(self):
        # FIXME: change for other years (2019 URL still valid for 2020)
        pdf_url = (
            "https://www.elections.ny.gov/NYSBOE/Elections/2019/ElectedOfficials.pdf"
        )
        filename, response = self.urlretrieve(pdf_url)
        text = convert_pdf(filename, type="text")
        columns = []
        lines = iter(text.decode().split("\n"))
        for ln in lines:
            if "ELECTED REPRESENTATIVES FOR NEW YORK STATE" in ln:
                next(lines)
                next(lines)
            else:
                columns.append(ln)

        serial = chain(
            (ln[:40].strip() for ln in columns), (ln[40:].strip() for ln in columns)
        )

        for ln in serial:
            if not ln:
                continue
            section = []
            while ln:
                section.append(ln)
                ln = next(serial)
            yield section

    def _identify_party(self):
        """
        Get the best available information on New York political party
        affiliations. Returns a dict mapping district to party for the
        New York State Assembly.

        The formatting of this page is pretty abysmal, so apologies
        about the dirtiness of this method.
        """
        # These may need to be changed, but should be mostly constant.
        NY_US_HOUSE_SEATS = 27
        NY_STATE_SENATE_SEATS = 63
        NY_STATE_ASSEMBLY_SEATS = 150

        assembly_affiliations = {}
        for r in self._scrape_from_pdf():
            m = re.match(r"Member of Assembly (\d+)", r[0])
            if not m:
                continue
            if r[2] == 'Vacant':
                continue
            district = m.group(1)
            _, _, party = r[1].partition(": ")

            assert party, "No party is indicated for district {}".format(district)
            assert (
                int(district) <= NY_STATE_ASSEMBLY_SEATS
            ), "bad district id {}".format(district)
            assert (
                district not in assembly_affiliations
            ), "Too many entries for district {}".format(district)

            assembly_affiliations[district] = party

        return assembly_affiliations

    def _parse_office(self, office_node):
        """
        Gets the contact information from the provided office.
        """
        office_name_text = self.get_node(
            office_node, './/span[@itemprop="name"]/text()'
        )

        if office_name_text is not None:
            office_name_text = office_name_text.strip()
        else:
            office_name_text = ()

        # Initializing default values for office attributes.
        office_name = None
        office_type = None
        street_address = None
        city = None
        state = None
        zip_code = None
        address = None
        phone = None
        fax = None

        # Determine office names/types consistent with Open States internal
        # format.
        if "Albany Office" in office_name_text:
            office_name = "Capitol Office"
            office_type = "capitol"
        elif "District Office" in office_name_text:
            office_name = "District Office"
            office_type = "district"
        else:
            # Terminate if not a capitol or district office.
            return None

        # Get office street address.
        street_address_text = self.get_node(
            office_node,
            './/div[@class="street-address"][1]/'
            'span[@itemprop="streetAddress"][1]/text()',
        )

        if street_address_text is not None:
            street_address = street_address_text.strip()

        # Get office city.
        city_text = self.get_node(office_node, './/span[@class="locality"][1]/text()')

        if city_text is not None:
            city = city_text.strip().rstrip(",")

        # Get office state.
        state_text = self.get_node(office_node, './/span[@class="region"][1]/text()')

        if state_text is not None:
            state = state_text.strip()

        # Get office postal code.
        zip_code_text = self.get_node(
            office_node, './/span[@class="postal-code"][1]/text()'
        )

        if zip_code_text is not None:
            zip_code = zip_code_text.strip()

        # Build office physical address.
        if (
            street_address is not None
            and city is not None
            and state is not None
            and zip_code is not None
        ):
            address = "{}\n{}, {} {}".format(street_address, city, state, zip_code)
        else:
            address = None

        # Get office phone number.
        phone_node = self.get_node(
            office_node, './/div[@class="tel"]/span[@itemprop="telephone"]'
        )

        if phone_node is not None:
            phone = phone_node.text.strip()

        # Get office fax number.
        fax_node = self.get_node(
            office_node, './/div[@class="tel"]/span[@itemprop="faxNumber"]'
        )

        if fax_node is not None:
            fax = fax_node.text.strip()
            if not validate_phone_number(fax):
                fax = None

        office = dict(
            name=office_name, type=office_type, phone=phone, fax=fax, address=address
        )

        return office

    def scrape(self, chamber=None):
        if chamber:
            yield from self.scrape_chamber(chamber)
        else:
            yield from self.scrape_upper_chamber("upper")
            yield from self.scrape_lower_chamber("lower")

    def scrape_upper_chamber(self, chamber):
        url = "https://www.nysenate.gov/senators-committees"

        page = self.lxmlize(url)

        legislator_nodes = page.xpath(
            '//div[contains(@class, "u-even") or contains(@class, "u-odd")]/a'
        )

        for legislator_node in legislator_nodes:
            legislator_url = legislator_node.attrib["href"]

            # Find element containing senator data.
            info_node = self.get_node(
                legislator_node, './/div[@class="nys-senator--info"]'
            )

            # Skip legislator if information is missing entirely.
            if info_node is None:
                warning = "No information found for legislator at {}."
                self.logger.warning(warning.format(legislator_url))
                continue

            # Initialize default values for legislator attributes.
            name = None
            district = None
            party = None
            photo_url = None

            # Find legislator's name.
            name_node = self.get_node(info_node, 'h4[@class="nys-senator--name"]')

            if name_node is not None:
                name = name_node.text.strip()
            else:
                # Skip the legislator if a name cannot be found.
                continue

            # Find legislator's district number.
            district_node = self.get_node(
                info_node, './/span[@class="nys-senator--district"]'
            )

            if district_node is not None:
                district_text = district_node.xpath(".//text()")[2]
                district = re.sub(r"\D", "", district_text)

            # Find legislator's party affiliation.
            party_node = self.get_node(
                district_node, './/span[@class="nys-senator--party"]'
            )

            if party_node is not None:
                party_text = party_node.text.strip()

                if party_text.startswith("(D"):
                    party = "Democratic"
                elif party_text.startswith("(R"):
                    party = "Republican"
                else:
                    raise ValueError(
                        "Unexpected party affiliation: {}".format(party_text)
                    )

            # Find legislator's profile photograph.
            photo_node = self.get_node(
                legislator_node, './/div[@class="nys-senator--thumb"]/img'
            )

            if photo_node is not None:
                photo_url = photo_node.attrib["src"]

            person = Person(
                name=name,
                district=district,
                party=party,
                primary_org=chamber,
                image=photo_url,
            )

            person.add_link(url)

            # Find legislator's offices.
            contact_url = legislator_url + "/contact"
            person.add_link(contact_url)

            self.scrape_upper_offices(person, contact_url)

            yield person

    def scrape_upper_offices(self, person, url):
        legislator_page = self.lxmlize(url)

        person.add_source(url)

        # Find legislator e-mail address.
        email_node = self.get_node(
            legislator_page,
            '//div[contains(concat(" ", normalize-space(@class), " "), '
            '" c-block--senator-email ")]/div/a[contains(@href, "mailto:")]',
        )

        if email_node is not None:
            email_text = email_node.attrib["href"]
            email = re.sub(r"^mailto:", "", email_text)
            email = re.sub(r"; .*", "", email)  # remove extraneous text
            person.add_contact_detail(type="email", value=email, note="Capitol Office")

        # Parse all offices.
        office_nodes = self.get_nodes(legislator_page, '//div[@class="adr"]')

        for office_node in office_nodes:
            office = self._parse_office(office_node)

            if office is not None:
                office_type = "{} Office".format(office["type"].title())
                if office["address"]:
                    person.add_contact_detail(
                        type="address", value=office["address"], note=office_type
                    )
                if office["phone"]:
                    person.add_contact_detail(
                        type="voice", value=office["phone"], note=office_type
                    )
                if office["fax"]:
                    person.add_contact_detail(
                        type="fax", value=office["fax"], note=office_type
                    )

    def scrape_lower_chamber(self, chamber):
        url = "http://assembly.state.ny.us/mem/?sh=email"

        page = self.lxmlize(url)

        district_affiliations = self._identify_party()

        assembly_member_nodes = self.get_nodes(
            page, '//div[@id="maincontainer"]/div[contains(@class, "email")]'
        )

        for assembly_member_node in self._split_list_on_tag(
            assembly_member_nodes, "emailclear"
        ):
            try:
                name_node, district_node, email_node = assembly_member_node
            except ValueError:
                name_node, district_node = assembly_member_node
                email_node = None

            name_anchor = self.get_node(name_node, './/a[contains(@href, "/mem/")]')
            name = name_anchor.text.strip()
            # Skip non-seats.
            if name == "Assembly Members":
                continue
            if "Assembly District" in name:
                continue

            email = None
            if email_node is not None:
                email_anchor = self.get_node(
                    email_node, './/a[contains(@href, "mailto")]'
                )
                if email_anchor is not None:
                    email = email_anchor.text.strip()

            if district_node is not None:
                district = district_node.text.rstrip("rthnds")

            party = district_affiliations[district].strip()
            if not party or party is None:
                self.critical(
                    "Party for {} (Assembly district {}) has not been listed yet".format(
                        name, district
                    )
                )
                if name in ("Rosenthal, Daniel", "Taylor, Al"):
                    party = "Democratic"
                elif name == "Tague, Chris":
                    party = "Republican"
                else:
                    raise ValueError(name)
                # If seats become empty, there may need to be a
                # `continue` added back in here, assuming no name
                # or other information was found

            photo_url = "http://assembly.state.ny.us/mem/pic/{0:03d}.jpg".format(
                int(district)
            )

            legislator_url = name_anchor.get("href")

            last, first = name.rsplit(", ", 1)
            name = " ".join([first, last])

            person = Person(
                name=name,
                district=district,
                party=party,
                primary_org=chamber,
                image=photo_url,
            )

            person.add_link(url)

            self.scrape_lower_offices(person, legislator_url, email)

            yield person

    def scrape_lower_offices(self, person, url, email):
        person.add_source(url)

        if email:
            person.add_contact_detail(type="email", value=email, note="Capitol Office")

        page = self.lxmlize(url)

        for data in page.xpath('//div[@class="addrcola"]'):
            office_name = data.xpath('./div[@class="officehdg"]/text()')[0]
            address = [
                line.strip()
                for line in data.xpath('./div[@class="officeaddr"]//text()')
            ]

            if "district" in office_name.lower():
                office_type = "District"
            else:
                office_type = "Capitol"

            address = [x.strip() for x in address if x.strip()]
            address.pop()

            fax = None
            phone = None
            if address:
                if address[-1].startswith("Fax: "):
                    fax = address.pop().replace("Fax: ", "")

                    if office_type == "Capitol" and re.match(r"^\d{3}[- ]\d{4}$", fax):
                        fax = "518-{}".format(fax.strip().replace(" ", "-"))

                if re.search(r"\d{3}[-\s]?\d{3}[-\s]?\d{4}", address[-1]):
                    phone = address.pop()

                address = "\n".join(address)

                if len(address) > 1:
                    person.add_contact_detail(
                        type="address", value=address, note=office_type + " Office"
                    )
                if phone:
                    person.add_contact_detail(
                        type="voice", value=phone, note=office_type + " Office"
                    )
                if fax:
                    person.add_contact_detail(
                        type="fax", value=fax, note=office_type + " Office"
                    )
