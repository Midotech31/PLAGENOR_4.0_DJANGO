"""Exercise Django's real SMTP backend against an isolated receiving server."""
import socketserver
import threading
from email import policy
from email.parser import BytesParser
from django.test import SimpleTestCase, override_settings
from notifications.emails import send_email_notification


class SMTPTransportTests(SimpleTestCase):
    def test_html_and_plain_text_are_received_over_smtp(self):
        received = []

        class Receiver(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(5)
                self.wfile.write(b'220 localhost ESMTP\r\n')
                while line := self.rfile.readline():
                    command = line.upper()
                    if command.startswith((b'EHLO', b'HELO')):
                        self.wfile.write(b'250 localhost\r\n')
                    elif command.startswith(b'DATA'):
                        self.wfile.write(b'354 Send message\r\n')
                        data = []
                        while (part := self.rfile.readline()) not in (b'.\r\n', b''):
                            data.append(part[1:] if part.startswith(b'..') else part)
                        received.append(b''.join(data))
                        self.wfile.write(b'250 Accepted\r\n')
                    elif command.startswith(b'QUIT'):
                        self.wfile.write(b'221 Goodbye\r\n')
                        return
                    else:
                        self.wfile.write(b'250 OK\r\n')

        with socketserver.TCPServer(('127.0.0.1', 0), Receiver) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                        EMAIL_HOST='127.0.0.1', EMAIL_PORT=server.server_address[1],
                        EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='', EMAIL_USE_SSL=False,
                        EMAIL_USE_TLS=False, EMAIL_TIMEOUT=5):
                    self.assertTrue(send_email_notification('recipient@example.test',
                        '[PLAGENOR] Vérification', '<p>Votre demande est enregistrée.</p>'))
            finally:
                server.shutdown()
                thread.join(timeout=5)
        self.assertEqual(len(received), 1)
        message = BytesParser(policy=policy.default).parsebytes(received[0])
        self.assertEqual(message['To'], 'recipient@example.test')
        self.assertEqual(message['Subject'], '[PLAGENOR] Vérification')
        self.assertIn('demande est enregistrée', message.get_body(preferencelist=('plain',)).get_content())
        self.assertIn('<p>', message.get_body(preferencelist=('html',)).get_content())
