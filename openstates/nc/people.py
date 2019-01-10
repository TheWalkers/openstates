from pupa.scrape import Scraper, Person
import lxml.html

party_map = {'Dem': 'Democratic',
             'Rep': 'Republican',
             'Una': 'Unaffiliated',
             'D': 'Democratic',
             'R': 'Republican',
             'U': 'Unaffiliated'}


def get_table_item(doc, name):
    # get span w/ item
    try:
        span = doc.xpath('//span[text()="{0}"]'.format(name))[0]
        # get neighboring td's span
        dataspan = span.getparent().getnext().getchildren()[0]
        if dataspan.text:
            return (dataspan.text + '\n' +
                    '\n'.join([x.tail for x in dataspan.getchildren()])).strip()
        else:
            return None
    except IndexError:
        return None


class NCPersonScraper(Scraper):
    def scrape(self, chamber=None):
        if chamber:
            yield from self.scrape_chamber(chamber)
        else:
            yield from self.scrape_chamber('upper')
            yield from self.scrape_chamber('lower')

    def scrape_chamber(self, chamber):
        url = "http://www.ncleg.net/gascripts/members/memberListNoPic.pl?sChamber="

        if chamber == 'lower':
            url += 'House'
        else:
            url += 'Senate'

        data = self.get(url).text
        doc = lxml.html.fromstring(data)
        doc.make_links_absolute('http://www.ncleg.net')
        rows = doc.xpath('/html/body/div/table/tr/td[1]/table/tr')

        for row in rows[1:]:
            party, district, full_name, counties = row.getchildren()

            party = party.text_content().strip("()")
            party = party_map[party]

            district = district.text_content().replace("District", "").strip()

            notice = full_name.xpath('span')
            if notice:
                notice = notice[0].text_content()
                # skip resigned legislators
                if 'Resigned' in notice or 'Deceased' in notice:
                    continue
            else:
                notice = None
            link = full_name.xpath('a/@href')[0]
            full_name = full_name.xpath('a')[0].text_content()
            full_name = full_name.replace(u'\u00a0', ' ')

            # scrape legislator page details
            lhtml = self.get(link).text
            ldoc = lxml.html.fromstring(lhtml)
            ldoc.make_links_absolute('http://www.ncleg.net')
            cols = ldoc.xpath('//div[contains(@class, "card-body")]/div/div')

            address = capitol_address = phone = capitol_phone = email = None

            # column 0 has an inline picture, no usable photo url

            # column 1 has addresses
            addr_ps = cols[1].xpath('//h6[contains(text(), "Mailing Address:")]/following-sibling::p')
            if addr_ps and addr_ps[0].text != 'None':
                capitol_address = address = '\n'.join([p.text.strip() for p in addr_ps])

            addr_ps = cols[1].xpath('//h6[contains(text(), "Legislative Office:")]/following-sibling::p')
            if addr_ps and addr_ps[0].text != 'None':
                capitol_address = '\n'.join([p.text.strip() for p in addr_ps[:2]])
                if addr_ps[2:]:
                    cap_phone_a = addr_ps[2].xpath('//a[starts-with(@href, "tel:")]')
                    if cap_phone_a:
                        capitol_phone = cap_phone_a[0].text

            # column 2 has phone and email
            phone_a = cols[2].xpath('//h6[contains(text(), "Phone:")]/ancestor::div/following-sibling::div/p/a[starts-with(@href, "tel:")]')
            if phone_a:
                phone = phone_a[0].text.strip()

            if phone and not capitol_phone:
                capitol_phone = phone

            email_a = cols[2].xpath('//h6[contains(text(), "Email:")]/ancestor::div/following-sibling::div/p/a[starts-with(@href, "mailto:")]')
            if email_a:
                capitol_email = email_a[0].text.strip()

            # column 3 has district map, skipped

            # save legislator
            person = Person(name=full_name, district=district,
                            party=party, primary_org=chamber)
            person.extras['counties'] = counties.text_content().split(', ')
            person.extras['notice'] = notice
            person.add_link(link)
            person.add_source(link)
            if address:
                person.add_contact_detail(type='address', value=address,
                                          note='District Office')
            if phone:
                person.add_contact_detail(type='voice', value=phone,
                                          note='District Office')
            if capitol_address:
                person.add_contact_detail(type='address', value=capitol_address,
                                          note='Capitol Office')
            if capitol_phone:
                person.add_contact_detail(type='voice', value=capitol_phone,
                                          note='Capitol Office')
            if capitol_email:
                person.add_contact_detail(type='email', value=capitol_email,
                                          note='Capitol Office')
            yield person
