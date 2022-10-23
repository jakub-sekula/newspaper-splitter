import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
import os
import logging

load_dotenv()

def send_mail(file, receiver):
	filename = file.split('/')[-1]
	logging.debug(f"Creating message {filename}")

	sender = os.getenv("SMTP_USER")

	message = MIMEMultipart()

	message["From"] = sender
	message["To"] = receiver
	message["Subject"] = f"{filename}"

	abc = "BLACK TITLE"
	msg_content = f'<p>Miłego czytania!</p>'
	message.attach(MIMEText((msg_content), "html"))

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

	# Setup SMTP server and send message
	logging.debug(f"Establishing SMTP connection with {os.getenv('SMTP_HOST')} on {os.getenv('SMTP_PORT')}")
	server = smtplib.SMTP(os.getenv("SMTP_HOST"), os.getenv("SMTP_PORT"))
	server.starttls()

	logging.debug(f"Logging in SMTP user {os.getenv('SMTP_USER')}")
	server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))

	logging.debug(f"Sending message from {sender} to {receiver}")
	server.sendmail(sender, [receiver], msg_full)
	server.quit()
	logging.info(f'Message {filename} sent successfully!')

	return 0
