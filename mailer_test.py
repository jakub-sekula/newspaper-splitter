from json import load
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from dotenv import load_dotenv
import os

load_dotenv()

# this is easy as piss lol

sender = os.getenv("SMTP_USER")
receiver = "seklerek@gmail.com"

message = MIMEMultipart()

abc = 'BLACK TITLE'
msg_content = '<h2>{title} <font color="green">TITLE HERE</font></h2>'.format(title=abc)
p1 = '<p>new line (paragraph 1)</p>'
p2 = '<p>Image below soon hopefully...</p>'
message.attach(MIMEText((msg_content+p1+p2), 'html'))

with open('image.png', 'rb') as image_file:
    message.attach(MIMEImage(image_file.read()))


message['From'] = sender
message['To'] = receiver
message['Subject'] = 'Python Test E-mail'
msg_full = message.as_string()

# Setup SMTP server and send message
server = smtplib.SMTP(os.getenv("SMTP_HOST"), os.getenv("SMTP_PORT"))
server.starttls()
server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
server.sendmail(sender,[receiver],msg_full)
server.quit()