import lxml.html
from openstates.scrape import Person, Scraper


class NoDetails(Exception):
    pass


SESSION_NUMBERS = {
    "2011": "62nd",
    "2013": "63rd",
    "2015": "64th",
    "2017": "65th",
    "2019": "66th",
}


class MTPersonScraper(Scraper):

    _roster_url = "https://leg.mt.gov/legislator-information/?session_select={}"
    _chamber_map = dict(lower="HD", upper="SD")

    def scrape(self, chamber=None, session=None):
        chambers = [chamber] if chamber else ["upper", "lower"]

        for chamber in chambers:
            if session_number >= "2019":
                url = "https://leg.mt.gov/legislator-information/csv"

            else:
                url = "http://leg.mt.gov/content/sessions/{}/{}{}Members.txt".format(
                    session_number, session, "Senate" if chamber == "upper" else "House"
                )
            yield from self.scrape_legislators(url, chamber=chamber)

    def scrape_legislators(self, url, chamber):
        district_type = {"upper": "SD", "lower": "HD"}[chamber]
        data = self.get(url).text
        data = data.replace('"""', '"')  # weird triple quotes
        data = data.splitlines()

        fieldnames = [
            "last_name",
            "first_name",
            "party",
            "district",
            "address",
            "city",
            "state",
            "zip",
            "email",
        ]
        csv_parser = csv.DictReader(data, fieldnames)

        district_leg_urls = self._district_legislator_dict()

        # Toss the row headers.
        next(csv_parser)

        for entry in csv_parser:
            if not entry:
                continue

            # District.
            district = entry["district"]
            hd_or_sd, district = district.split()

            if hd_or_sd != district_type:
                continue

            # Party.
            party_letter = entry["party"]
            party = {"D": "Democratic", "R": "Republican"}[party_letter]

            # Get full name properly capped.
            fullname = "%s %s" % (
                entry["first_name"].title(),
                entry["last_name"].title(),
            )

            legislator = Person(
                name=fullname,
                primary_org=chamber,
                district=district,
                party=party,
                image=entry.get("photo_url", ""),
            )
            legislator.extras["given_name"] = entry["first_name"].title()
            legislator.extras["family_name"] = entry["last_name"].title()
            legislator.add_source(url)

            # Get any info at the legislator's detail_url.
            deets = {}
            try:
                detail_url = district_leg_urls[hd_or_sd][district]
                deets = self._scrape_details(detail_url)
            except KeyError:
                self.warning(
                    "Couldn't find legislator URL for district {} {}, likely retired; skipping".format(
                        hd_or_sd, district
                    )
                )
                continue
            except NoDetails:
                self.logger.warning("No details found at %r" % detail_url)
                continue
            else:
                legislator.add_source(detail_url)
                legislator.add_link(detail_url)

            # Get the office.
            address = "\n".join(
                [
                    " ".join(
                        [w.title() for w in entry["address"].split(" ") if w != "PO"]
                    ),
                    "%s, %s %s" % (entry["city"].title(), entry["state"], entry["zip"]),
                ]
            )
            legislator.add_contact_detail(
                type="address", value=address, note="District Office"
            )

            phone = deets.get("phone")
            fax = deets.get("fax")
            email = deets.get("email")
            if phone:
                legislator.add_contact_detail(
                    type="voice", value=phone, note="District Office"
                )
            if fax:
                legislator.add_contact_detail(
                    type="fax", value=fax, note="District Office"
                )
            if email and re.match(r"[a-zA-Z0-9\.\_\%\+\-]+@\w+\.[a-z]+", email):
                legislator.add_contact_detail(
                    type="email", value=email, note="District Office"
                )

            yield legislator

    def _district_legislator_dict(self):
        """Create a mapping of districts to the legislator who represents
        each district in each house.

        Used to get properly capitalized names in the legislator scraper.
        """
        res = {"HD": {}, "SD": {}}

        url = "https://leg.mt.gov/legislator-information/"

        # Go the legislator-information page.
        doc = self.url_xpath(url)
        doc.make_links_absolute(url)
        table = doc.xpath('//table[@id="reports-table"]')[0]

        for tr in table.xpath("tbody/tr"):

            email, name, party, seat, phone = tr.xpath("td")

            # Skip header rows and retired legislators
            if (
                not name.text_content().strip()
                or " resigned " in name.text_content().lower()
            ):
                continue

            # Get link to the member's page.
            detail_url = name.xpath("a/@href")[0]

            # Get the members district so we can match the
            # profile page with its csv record.
            chamber, district = seat.text_content().split()
            res[chamber][district] = detail_url

        return res

    def _scrape_details(self, url):
        """
        Scrape the member's bio page.

        Legislator images are rendered as inline pngs, so no photo url is
        currently available.
        """
        details = {}
        doc = self.url_xpath(url)

        phone_email_p = doc.xpath('//div[contains(h4, "Contact Information")]/p')[1]

        for line in phone_email_p.text_content().split("\n"):
            key, _, value = [s.strip() for s in line.partition(":")]
            if not key and value:
                continue

            if key == "Email" and re.match(
                r"[a-zA-Z0-9\.\_\%\+\-]+@\w+\.[a-z]+", value
            ):
                details["email"] = value

            elif key == "Primary ph" and re.match(r"\(\d{3}\) \d{3}\-\d{4}", value):
                details["phone"] = value

            elif (
                key == "Secondary ph"
                and re.match(r"\(\d{3}\) \d{3}\-\d{4}", value)
                and "phone" not in details
            ):
                details["phone"] = value

        return details
