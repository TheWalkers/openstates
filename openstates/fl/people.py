import re
import tempfile
import lxml
import logging
from urllib import parse
from pupa.scrape import Scraper, Person
from pupa.utils import convert_pdf
from spatula import Spatula, Page
from .utils import fix_name

log = logging.getLogger('fl')


class SenDetail(Page):
    list_xpath = '//h4[contains(text(), "Office")]'

    def handle_list_item(self, office):
        (name, ) = office.xpath('text()')
        if name == "Tallahassee Office":
            type_ = 'capitol'
        else:
            type_ = 'district'

        address_lines = [x.strip() for x in
                         office.xpath('following-sibling::div[1]')[0].text_content().splitlines()
                         if x.strip()]

        clean_address_lines = []
        fax = phone = None
        PHONE_RE = r'\(\d{3}\)\s\d{3}\-\d{4}'
        after_phone = False

        for line in address_lines:
            if re.search(r'(?i)open\s+\w+day', address_lines[0]):
                continue
            elif 'FAX' in line:
                fax = line.replace('FAX ', '')
                after_phone = True
            elif re.search(PHONE_RE, line):
                phone = line
                after_phone = True
            elif not after_phone:
                clean_address_lines.append(line)

        if phone:
            self.obj.add_contact_detail(type='voice', value=phone, note=type_)
        if fax:
            self.obj.add_contact_detail(type='fax', value=fax, note=type_)

        # address
        address = "\n".join(clean_address_lines)
        address = re.sub(r'\s{2,}', " ", address)
        if address:
            self.obj.add_contact_detail(type='address', value=address, note=type_)

    def handle_page(self):
        list(super().handle_page())
        email = self.doc.xpath('//a[contains(@href, "mailto:")]')[0].get('href').split(':')[-1]
        self.obj.add_contact_detail(type='email', value=email)

        self.obj.image = self.doc.xpath('//div[@id="sidebar"]//img/@src').pop()


class SenList(Page):
    url = "http://www.flsenate.gov/Senators/"
    list_xpath = "//a[@class='senatorLink']"

    def handle_list_item(self, item):
        name = " ".join(item.xpath('.//text()'))
        name = re.sub(r'\s+', " ", name).replace(" ,", ",").strip()

        if 'Vacant' in name:
            return

        district = item.xpath("string(../../td[1])")
        party = item.xpath("string(../../td[2])")
        if party == 'Democrat':
            party = 'Democratic'

        leg_url = item.get('href')

        parts = name.split(', ')
        parts[:2] = parts[1::-1]  # reverse first two
        name = ' '.join(parts)
        leg = Person(name=name, district=district, party=party,
                     primary_org='upper', role='Senator')
        leg.add_link(leg_url)
        leg.add_source(self.url)
        leg.add_source(leg_url)

        self.scrape_page(SenDetail, leg_url, obj=leg)

        return leg


class RepList(Page):
    url = "http://www.myfloridahouse.gov/Sections/Representatives/representatives.aspx"
    directory_pdf_url = 'http://www.myfloridahouse.gov/FileStores/Web/'\
                        'HouseContent/Approved/ClerksOffice/HouseDirectory.pdf'
    list_xpath = '//div[@id="mb-2"]//div[@class="team-box"]'

    def handle_page(self):
        self.member_emails = self._load_emails_from_directory_pdf()
        self.claimed_member_emails = dict()
        return super(RepList, self).handle_page()

    def _load_emails_from_directory_pdf(self):
        """
        Load the house PDF directory and convert to LXML - needed to
        find email addresses which are gone from the website.
        """
        with tempfile.NamedTemporaryFile() as temp:
            self.scraper.urlretrieve(self.directory_pdf_url, temp.name)
            directory = lxml.etree.fromstring(convert_pdf(temp.name, 'xml'))

        # pull out member email addresses from the XML salad produced
        # above - there's no obvious way to match these to names, but
        # fortunately they have names in them
        return set(directory.xpath(
            '//text[contains(text(), "@myfloridahouse.gov")]/text()'))

    def handle_list_item(self, item):
        link = item.xpath('./a')[0]
        info = link.xpath('./div[@class="team-txt"]')[0]
        name = info.xpath('./h5/text()')[0].strip()

        info_text = info.text_content()

        if 'Vacant' in info_text or 'Resigned' in info_text or 'Pending' in info_text:
            return

        if 'Republican' in info_text:
            party = 'Republican'
        elif 'Democrat' in info_text:
            party = 'Democratic'
        else:
            print("No party found!", info_text)

        district = re.search(r'District: (\d+)', info_text).group(1)

        leg_url = link.get('href')
        split_url = parse.urlsplit(leg_url)
        member_id = parse.parse_qs(split_url.query)['MemberId'][0]
        image = "http://www.flhouse.gov/FileStores/Web/Imaging/Member/{}.jpg".format(member_id)

        orig_name = name
        name = fix_name(name)
        rep = Person(name=name, district=district, party=party, primary_org='lower',
                     role='Representative', image=image)
        rep.add_link(leg_url)
        rep.add_source(leg_url)
        rep.add_source(self.url)

        self.scrape_page(RepDetail, leg_url, obj=rep)

        # look for email in the list from the PDF directory - ideally
        # we'd find a way to better index the source data which
        # wouldn't require guessing the email, but this does at least
        # confirm that it's correct

        # deal with some stuff that ends up in name that won't work in
        # email, spaces, quotes, high latin1
        email_name = orig_name.replace('"', '')\
                             .replace("La ", "La")\
                             .replace("ñ", "n")
        (last, *other) = re.split(r'[-\s,]+', email_name)

        # deal with a missing nickname used in an email address
        if "Patricia" in other:
            other.append("Pat")

        # search through all possible first names and nicknames
        # present - needed for some of the more elaborate concoctions
        found_email = False
        for first in other:
            email = '%s.%s@myfloridahouse.gov' % (first, last)
            if email in self.member_emails:
                # it's bad if we can't uniquely match emails, so throw an error
                if email in self.claimed_member_emails:
                    raise ValueError(
                        "Email address %s matches multiple reps - %s and %s." %
                        (email, rep.name, self.claimed_member_emails[email]))

                self.claimed_member_emails[email] = rep.name

                rep.add_contact_detail(type='email',
                                       value=email,
                                       note='Capitol Office')
                rep.add_source(self.directory_pdf_url)

                found_email = True

                break

        if not found_email:
            log.warning('Rep %s does not have an email in the directory PDF.' %
                        (rep.name,))

        return rep


class RepDetail(Page):
    def handle_page(self):
        self.scrape_office('Capitol Office')
        self.scrape_office('District Office')

    def scrape_office(self, name):
        pieces = [x.tail.strip() for x in
                  self.doc.xpath('//strong[text()="{}"]/following-sibling::br'.format(name))]

        if not pieces:
            # TODO: warn?
            return
        address = []

        for piece in pieces:
            if piece.startswith('Phone:'):
                # Phone: \r\n     (303) 111-2222
                if re.search(r'\d+', piece):
                    phone = piece.split(None, 1)[1]
                else:
                    phone = None
            else:
                address.append(re.sub(r'\s+', ' ', piece))

        type_ = 'capitol' if 'Capitol' in name else 'district'

        self.obj.add_contact_detail(type='address', value='\n'.join(address), note=type_)
        if phone:
            self.obj.add_contact_detail(type='voice', value=phone, note=type_)


class FlPersonScraper(Scraper, Spatula):

    def scrape(self):
        yield from self.scrape_page_items(SenList)
        yield from self.scrape_page_items(RepList)
