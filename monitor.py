import imaplib
import email
import requests
import json
import MySQLdb
import time
from time import strftime, localtime

imapserver = "imap.gmail.com"
emuser     = "#"
empw       = "#"
inbox      = "inbox"
# dir        = "prints/"
api        = "#"
host       = "http://0.0.0.0:5000/"
dbhost     = "#"
dbuser     = "#"
dbpw       = "#"
dbname     = "#"

def init(spec):
    mail = imaplib.IMAP4_SSL(imapserver)
    mail.login(emuser, empw)
    mail.select(inbox)
    if spec == 2:           #provides option to either initialize both mail and DB or just mail
        db = MySQLdb.connect(host=dbhost, user=dbuser, passwd=dbpw, db=dbname)
        return [mail, db]
    elif spec == 1:
        return mail

def structhandler(struct):
    list = []
    for j, k in enumerate(struct):
        if k == '("FILENAME"':
            count = 1
            val   = struct[j + count]
            while val[-3] != '"':
                count += 1
                val   += " " + struct[j + count]
            list.append(val[1:-3])
        elif k == '"FILENAME"':
            count = 1
            val   = struct[j + count]
            while val[-1] != '"':
                count += 1
                val   += " " + struct[j + count]
            list.append(val[1:-1])
    return list


def emaildict(uid, mailobj, cursor):
    # RFC822 is the body of the email, BODYSTRUCTURE is the structure of the email that you can extract filenames from
    data    = mailobj.uid('fetch', uid, '(RFC822 BODYSTRUCTURE)')[1]
    bstruct = data[1].split()        # split bodystructure
    list    = structhandler(bstruct)                    # holds list of attachment filenames
    if list:
        # has attachments, extract email info and add to result
        raw = email.message_from_string(data[0][1])
        arr = raw['From'].split()
        filename = dbhandler(uid, raw['Subject'], arr[-1][1:-1], list, raw, cursor)
        return filename         #null if valid attachment, else returns name of file


def dbhandler(uid, subj, addr, attachments, raw, c):
    print("email id: %s, subj: %s, addr: %s, attachments: %s" % (uid, subj, addr, attachments))
    c.execute("""INSERT INTO ADDR_UID(ADDR,UID) VALUES(%s , %s)""", (addr, uid))
    c.fetchone()
    c.execute("""SELECT * FROM V_A""")
    time.sleep(1)       # load times were messing it up
    verifd  = c.fetchall()
    time.sleep(1)
    print(str(verifd))
    for i in verifd:
        print(str(i['EMAIL_ADDRESS']) + ":" + str(addr))
        if i['EMAIL_ADDRESS'] == addr and i['SECRET'] == subj:
            maildata = raw
            filename = extract(maildata)
            print(i['SECRET'] + ":" + filename)
            if filename:
                c.execute("""INSERT INTO V_M(UID, ADDR, SUBJ, VALID_ATTACHMENT) VALUES(%s, %s, %s, %s)""",
                               (uid, addr, subj, 1))
                print("Print added with name " + str(filename) + "with secret " + i['SECRET'])
                return filename
            c.execute("""INSERT INTO V_M(UID, ADDR, SUBJ, VALID_ATTACHMENT) VALUES(%s, %s, %s, %s)""",
                   (uid, addr, subj, 0))
    print("Mail with UID = %s has an invalid file or incorrect secret, not added to queue." % str(uid))
    return


def extract(raw):
    for part in raw.walk():
        if part.get_content_type() == 'application/octet-stream' or part.get_content_type() == 'application/vnd.ms-pki.stl':
            name = part.get_param('name')
            if name[-4:] == '.stl':
                print(name)
                # path = os.path.join(dir, name)
                f = open(name, 'wb')
                f.write(part.get_payload(None, True))
                f.close()
                return name


def getPrinterStatus(session, url):
    url += "api/printer"
    r    = session.get(url).json()
    print(json.dumps(r))


def getJobStatus(session,url):
    url += "api/job"
    r    = session.get(url).json()
    print(json.dumps(r))


def printHome(session, url):
    url += "api/printer/printhead"
    session.headers['Content-Type'] = 'application/json'
    com  = json.dumps({"command": "home", "axes": ["x", "y"]})
    r    = session.post(url, data=com)


def addFile(session, url, filename):
    url += "api/files/local"
    file = {'file': open(filename)}
    session.post(url, files=file)


def printFile(session, url, filename):
    url += "api/files/local/" + str(filename)
    session.headers['Content-Type'] = 'application/json'
    com  = json.dumps({"command": "slice",
                       "gcode": filename[:-4] + ".gcode",
                       "profile": "cura",
                       "position": {"x": 100, "y": 100},
                       "print": "true"})
    session.post(url, data=com)

def queuecheck(session, url):
    url += "api/job"
    r    = session.get(url).json()
    print(json.dumps(r))
    #check DB for any jobs, with ones, if none, start, change boolean
    #if current jobs, get job api json, push time remaining?
    #check to see if querying job api when job is done returns something helpful:
    #this can be used to tell someone that the button needs to be pressed at the printer
    #button press removes current job, starts next if available
    #then need to do quality control tests
    #tomorrow: button first, then API calls, then code


def main():
    ini     = init(2)
    mail,db = ini[0], ini[1]
    d       = db.cursor(MySQLdb.cursors.DictCursor)
    count   = -1        # starts at last index of array
    newDB   = -1        # arbitrary value, base value surely NEQ to any UID
    uids    = mail.uid('search', None, "ALL")[1][0].split()
    # uids = mail.uid('search', '(UID 13000:*)', "ALL")[1][0].split()
    curr    = int(uids[count])
    while True:
        if d.execute("""SELECT UID FROM ADDR_UID ORDER BY UID DESC LIMIT 5"""):     # returns false if empty result set
            newDB = d.fetchone()['UID']
        if newDB == curr:
            print("No new emails, most recent email in DB has UID %s" % uids[-1])
            mail.logout()
            d.close()
            time.sleep(10)
            mail    = init(1)
            d       = db.cursor(MySQLdb.cursors.DictCursor)
            count   = -1
            uids    = mail.uid('search', None, "ALL")[1][0].split()
            # uids  = mail.uid('search', '(UID 13000:*)', "ALL")[1][0].split()
            curr    = int(uids[count])
        else:
            d = db.cursor(MySQLdb.cursors.DictCursor)
            s = requests.Session()
            s.headers['X-Api-Key'] = api
            while newDB != curr and abs(count) < len(uids):
                print(str(curr) + " " + str(uids[count]))
                try:
                    currfile  = emaildict(curr, mail, d)
                    print(currfile)
                    if currfile:
                        addFile(s, host, currfile)
                        #d.execute("""INSERT INTO JOBS(UID, DATE, FILENAME) VALUES(%s, %s, %s)""",
                        #               curr, strftime("%Y-%m-%d %H:%M:%S", localtime()), currfile)
                        #d.fetchone()
                    count -= 1
                    curr   = int(uids[count])
                except Exception as e:
                    print("Fatal error: " + str(e))
                    mail.logout()
                    return
            main()


if __name__ == '__main__':
    main()




