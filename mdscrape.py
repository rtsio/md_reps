#!/usr/bin/python
# Rostislav Tsiomenko
# rostislav.tsiomenko@gmail.com
# Scrapes Maryland State Legislature site
# TODO: use a proper parser (like BeautifulSoup)
import urllib2
import re
import MySQLdb
from datetime import date

# From http://stackoverflow.com/questions/2217488/age-from-birthdate-in-python
def calculate_age(month, day, year):
    month_dict = {"January":1,"February":2,"March":3,"April":4, "May":5, "June":6,
                  "July":7,"August":8,"September":9,"October":10,"November":11,"December":12}
    month_int = month_dict[month]
    today = date.today()
    born = date(int(year), month_int, int(day))
    try:
        birthday = born.replace(year=today.year)
    # Leap year
    except ValueError:
        birthday = born.replace(year=today.year, day=born.day-1)
    if birthday > today:
        return today.year - born.year - 1
    else:
        return today.year - born.year

host = "rtsio.com"
user = "replacewithyourown"
password = "replacewithyourown"
database = "rtsio_md"
db = MySQLdb.connect(host, user, password, database, charset='utf8')
cursor = db.cursor()

# Read directory
directory = urllib2.urlopen('http://mgaleg.maryland.gov/webmga/frmmain.aspx?pid=legisrpage&tab=subject6').read()
senator_count = 0
delegate_count = 0
# Find all legislators, note 142 are listed on site instead of 141
regex = re.compile(r'frmMain\.aspx\?pid=sponpage&tab=subject6&id=(.*?)&stab=01&ys=2013RS')
for legislator in regex.findall(directory):

    # Format of this list: type (sen/del), name, district #, county, party, 
    #                      ann. address, intrm. address, phone, email, assignments, 
    #                      tenure, total bills, primary sponsor bills, co-sponsor
    #                      bills, bills by request, birthdate is visible (boolean),
    #                      hometown is visible (boolean), hometown (if visible), 
    #                      birthdate (if visible), age (if birthdate is visible)
    current_legislator = []

    # Download individual page and process it
    current_page = urllib2.urlopen('http://mgaleg.maryland.gov/webmga/frmMain.aspx?pid=sponpage&tab=subject6&id=' + legislator + '&stab=01&ys=2013RS').read()
    
    # Regex is a very bad way to parse DOM
    senator = re.search(r'Senator (.*)</h2>',current_page)
    delegate = re.search(r'Delegate (.*)</h2',current_page)
    # This is a pretty inefficient way to tell if someone is a Senator or Delegate, 
    # but the entire General Assembly site markup is not very semantic
    if senator:
        current_legislator.append("senator")
        current_legislator.append(senator.group(1))
        senator_count += 1
    else:
        current_legislator.append("delegate")
        current_legislator.append(delegate.group(1))
        delegate_count += 1
    
    # Get district, county, etc. up to email
    district = re.search(r'District (.{1,3}), (.*)</h3',current_page)
    current_legislator.append(district.group(1))
    current_legislator.append(district.group(2))
    current_legislator.append(re.search(r'Party Affiliation:</th><td>(.*?)</td>', current_page).group(1))
    current_legislator.append(re.search(r'Annapolis Address:</th><td>(.*?)</td>', current_page).group(1).replace("<br />", ", "))
    current_legislator.append(re.search(r'Interim Address:</th><td>(.*?)</td>', current_page).group(1).replace("<br />", ", "))
    current_legislator.append(re.search(r'<th>Phone<br />.*?<td>(.*?)</td>', current_page).group(1).replace("<br />", ", "))
    email = re.search(r'a href="mailto:(.*?)\?body', current_page)
    # Some delegates only have a contact link and no email
    if email:
        current_legislator.append(email.group(1))
    else:
        current_legislator.append("no email listed")
    
    # Get assignments and tenure
    current_legislator.append(re.search(r'Current Assignments:</th><td>(.*?)</td>', current_page).group(1).replace("<br />", ", "))
    current_legislator.append(re.search(r'Tenure:</th><td>(.*?)</td>', current_page).group(1))
    # Total bills, Primary sponsor, Co-sponsor, By request from 2nd tab
    session_page = urllib2.urlopen('http://mgaleg.maryland.gov/webmga/frmMain.aspx?stab=02&pid=sponpage&id=' + legislator + '&tab=subject6&ys=2013RS').read()
    bills = re.search('Total Bills: (\d*) \(Primary Sponsor: (\d*), Co-sponsor: (\d*), By Request: (\d*)\)</h4>', session_page)
    if bills:
        current_legislator.append(bills.group(1))
        current_legislator.append(bills.group(2))
        current_legislator.append(bills.group(3))
        current_legislator.append(bills.group(4))
    else:
        current_legislator.extend([0,0,0,0])
    
    # Hometown/Birthdate from 3rd town; some pages do not show this information, so it's optional
    bio_page = urllib2.urlopen('http://mgaleg.maryland.gov/webmga/frmMain.aspx?stab=03&pid=sponpage&id=' + legislator + '&tab=subject6&ys=2013RS').read()
    birth_visible = True
    hometown_visible = True

    # Since birth dates and hometowns are listed in wildly different ways on the site, 
    # here is a dict of all the major exceptions that the regex won't capture, since these
    # details can be assumed to stay static
    # Key: name as it appears on the site
    # Value: blob separated by | char, 'birth_visible|hometown_visible|Hometown|Month|Day|Year'
    exceptions = {'Jennie M. Forehand':'no|yes|Nashville, Tennessee',
                  'Bill Ferguson':'yes|yes|Silver Spring, Maryland|April|15|1983',
                  'Richard F. Colburn':'yes|yes|Easton, Maryland|February|9|1950',
                  'Roger P. Manno':'yes|no|April|26|1966',
                  'Douglas J. J. Peters':'yes|no|December|28|1963',
                  'E. J. Pipkin':'no|yes|Maryland',
                  'Catherine E. Pugh':'no|yes|Norristown, Pennsylvania',
                  'James N. Robey':'yes|yes|Baltimore, Maryland|January|18|1941',
                  'Kathy Afzali':'yes|yes|San Francisco, Maryland|May|27|1957',
                  'Pamela Beidle':'yes|yes|Maryland|July|1|1951',
                  'Ana Sol Gutierrez':'yes|yes|El Salvador|January|11|1942',
                  'Carolyn J. B. Howard':'no|yes|DeLand, Florida',
                  'Hattie N. Harrison':'no|yes|Lancaster, South Carolina', 
                  'Sally Jameson':'yes|yes|Prince Frederick, Maryland|May|26|1952',
                  'Ariana B. Kelly':'no|yes|Bethesda, Maryland|',
                  'Aruna Miller':'yes|yes|Hyderabad, India|November|6|1964',
                  'Shirley Nathan-Pulliam':'yes|yes|Trelawny, Jamaica|May|20|1939',
                  'Wayne Norman':'no|yes|Baltimore, Maryland',
                  'David D. Rudolph':'yes|yes|Summit, New Jersey|June|12|1949',
                  'Jay A. Jacobs':'no|yes|Rock Hall, Maryland',
                  'Barbara Robinson':'no|yes|Alexandria City, Alabama',
                  'Joseline A. Pena-Melnyk':'yes|yes|Dominican Republic|June|27|1966',
                  'Michael G. Summers':'yes|yes|North Carolina|November|19|1972',
                  'Geraldine Valentino-Smith':'yes|yes|Brooklyn, New York|March|5|1964',
                  'C. T. Wilson':'yes|yes|Missouri|February|20|1972',
                  'Kriselda Valderrama':'no|yes|Washington, DC'
                  }
    age = 0
    if current_legislator[1] in exceptions:
        blob = exceptions[current_legislator[1]].split("|")
        if blob[0] == "no":
            birth_visible = False
            hometown = blob[2]
        if blob[1] == "no":
            hometown_visible = False
            birth_month = blob[2]
            birth_day = blob[3]
            birth_year = blob[4]
        if blob[0] == "yes" and blob[1] == "yes":
            hometown = blob[2]
            birth_month = blob[3]
            birth_day = blob[4]
            birth_year = blob[5]
    else:
        bio_regex = re.search(r'Born, (.*?,.*?), (\D*?) (\d*?), (\d*?)\s*</td>', bio_page)
        hometown = bio_regex.group(1)
        birth_month = bio_regex.group(2).replace(',', '')
        birth_day = bio_regex.group(3)
        birth_year = bio_regex.group(4)
    if birth_visible:
        age = calculate_age(birth_month, birth_day, birth_year)        
    current_legislator.append(birth_visible)
    current_legislator.append(hometown_visible)
    if hometown_visible:
        current_legislator.append(hometown)
    if birth_visible:
        current_legislator.append(birth_month + " " + birth_day + " " + birth_year)
        current_legislator.append(age)

    # Beam to db depending on if hometown/birth is visible; it may be better to just use
    # strings (for example, "none") instead of NULL/None, and deal with it on the frontend
    if hometown_visible and birth_visible:
        cursor.execute("""INSERT INTO `legislators` VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", 
                       (0, current_legislator[0], current_legislator[1], current_legislator[2], current_legislator[3], current_legislator[4], current_legislator[5],
                        current_legislator[6], current_legislator[7], current_legislator[8], current_legislator[9], current_legislator[10], 
                        int(current_legislator[11]), int(current_legislator[12]), int(current_legislator[13]), int(current_legislator[14]),
                        1, 1, current_legislator[17], current_legislator[18], age))
        db.commit()
    elif not birth_visible:
        cursor.execute("""INSERT INTO `legislators` VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", 
                       (0, current_legislator[0], current_legislator[1], current_legislator[2], current_legislator[3], current_legislator[4], current_legislator[5],
                        current_legislator[6], current_legislator[7], current_legislator[8], current_legislator[9], current_legislator[10], 
                        int(current_legislator[11]), int(current_legislator[12]), int(current_legislator[13]), int(current_legislator[14]),
                        0, 1, current_legislator[17], None, None))
        db.commit()
    elif not hometown_visible:
        cursor.execute("""INSERT INTO `legislators` VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", 
                       (0, current_legislator[0], current_legislator[1], current_legislator[2], current_legislator[3], current_legislator[4], current_legislator[5],
                        current_legislator[6], current_legislator[7], current_legislator[8], current_legislator[9], current_legislator[10], 
                        int(current_legislator[11]), int(current_legislator[12]), int(current_legislator[13]), int(current_legislator[14]),
                        1, 0, None, current_legislator[18], age))
        db.commit()

print "Senators downloaded: " + str(senator_count)
print "Delegates downloaded: " + str(delegate_count)
db.close()
