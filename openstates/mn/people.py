import re

from pupa.scrape import Person, Scraper
from spatula import Page, Spatula
from openstates.utils import validate_phone_number, validate_email_address

PARTIES = {
    'DFL': 'Democratic-Farmer-Labor',
    'R': 'Republican',
}


class SenList(Page):
    url = 'https://www.senate.mn/members/index.php'
    list_xpath = '//div[@id="alphabetically"]//div[@class="media my-3"]'

    def handle_list_item(self, item):
        photo_url = item.xpath('img/@src')[0]
        body = item.xpath('div')[0]

        url = body.xpath('h5/a/@href')[-1]

        name_text = body.xpath('h5/a/b/text()')[-1]  # last, to skip titles
        name_match = re.match(r'^(.+)\(([0-9]{2}), ([A-Z]+)\)$', name_text)
        name = name_match.group(1).strip()
        district = name_match.group(2).lstrip('0').upper()
        party_text = name_match.group(3)
        party = PARTIES[party_text]

        email_text = body.xpath('div[@class="form-check-inline"]/a/text()')[-1].strip()
        if validate_email_address(email_text):
            email = email_text
        else:
            email = None

        addr1 = body.xpath('div[@class="form-check-inline"]/text()')[0]
        info_texts = [x.strip() for x in body.xpath(
            './text()[normalize-space() and preceding-sibling::br]'
        ) if x.strip()]
        address = '\n'.join([addr1, info_texts[0]])

        phone = None
        phone_text = info_texts[1]
        if validate_phone_number(phone_text):
            phone = phone_text

        rep = Person(name=name, district=district, party=party,
                     primary_org='lower', role='Representative',
                     image=photo_url)
        rep.add_link(url)
        rep.add_contact_detail(type='address', value=address, note='capitol')
        if phone:
            rep.add_contact_detail(type='voice', value=phone, note='capitol')

        if email:
            rep.add_contact_detail(type='email', value=email, note='capitol')
        rep.add_source(self.url)

        yield rep


class RepList(Page):
    url = 'https://www.house.leg.state.mn.us/members/list'
    list_xpath = '//div[@id="Alpha"]//div[@class="media my-3"]'

    name_pattern = re.compile(r'^(.+)\(([0-9]{2}[AB]), ([A-Z]+)\)$')

    def handle_list_item(self, item):
        photo_url = item.xpath('img/@src')[0]
        body = item.xpath('div')[0]

        url = body.xpath('h5/a/@href')[-1]

        name_text = body.xpath('h5/a/b/text()')[-1]  # last, to skip titles
        name_match = self.name_pattern.match(name_text)
        name = name_match.group(1).strip()
        district = name_match.group(2).lstrip('0').upper()
        party_text = name_match.group(3)
        party = PARTIES[party_text]

        email_text = body.xpath('a/text()')[0].strip()
        if validate_email_address(email_text):
            email = email_text
        else:
            email = None

        info_texts = [x.strip() for x in body.xpath(
            './text()[normalize-space() and following-sibling::br]'
        ) if x.strip()]
        address = '\n'.join(info_texts[:2])

        phone = None
        phone_text = info_texts[2]
        if validate_phone_number(phone_text):
            phone = phone_text

        rep = Person(name=name, district=district, party=party,
                     primary_org='lower', role='Representative',
                     image=photo_url)
        rep.add_link(url)
        rep.add_contact_detail(type='address', value=address, note='capitol')
        if phone:
            rep.add_contact_detail(type='voice', value=phone, note='capitol')

        if email:
            rep.add_contact_detail(type='email', value=email, note='capitol')
        rep.add_source(self.url)

        yield rep


class MNPersonScraper(Scraper, Spatula):
    def scrape(self):
        yield from self.scrape_page_items(SenList)
        yield from self.scrape_page_items(RepList)
