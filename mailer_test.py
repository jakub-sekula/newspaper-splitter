from json import load
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
import os

load_dotenv()

# this is easy as piss lol


def send_mail(file):

	sender = os.getenv("SMTP_USER")
	receiver = os.getenv("SMTP_USER")

	message = MIMEMultipart()
	print("message created")
	print("file:", file)

	message["From"] = sender
	message["To"] = receiver
	message["Subject"] = file

	print(sender,receiver,file)

	abc = "BLACK TITLE"
	msg_content = f'<h2>{abc} <font color="green">TITLE HERE</font></h2>'
	p1 = "<p>new line (paragraph 1)</p>"
	p2 = "<p>Image below soon hopefully...</p>"
	message.attach(MIMEText((msg_content + p1 + p2), "html"))

	with open(file, "rb") as attachment:
		obj = MIMEBase("application", "octet-stream")
		obj.set_payload((attachment).read())
		encoders.encode_base64(obj)
		obj.add_header(
			"Content-Disposition",
			f"attachment; filename={file}",
		)
		message.attach(obj)

	msg_full = message.as_string()
	# print(msg_full)

	# Setup SMTP server and send message
	server = smtplib.SMTP_SSL(os.getenv("SMTP_HOST"), os.getenv("SMTP_PORT"))
	# server.starttls()
	server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
	server.sendmail(sender, [receiver], msg_full)
	server.quit()
	print('message sent!')
