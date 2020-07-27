import os
import io
import sys
import logging
import json
import math
import tempfile
import datetime

import google.auth
import google.auth.transport.requests as tr_requests
import numpy as np

from google.cloud import storage, datastore, firestore
from google.resumable_media.requests import ChunkedDownload, ResumableUpload

from PIL import Image
from PyPDF2 import PdfFileReader, PdfFileWriter, utils

logging.getLogger().setLevel(logging.INFO)


class DBDatastore(object):
    def __init__(self, db_name):
        self.db_client = datastore.Client()
        self.db_name = db_name

    def update_status(self, object_id, status):
        entity_key = self.db_client.key(self.db_name, object_id)
        entity = self.db_client.get(entity_key)

        if not entity:
            return False

        entity['status'] = status
        entity['updated_at'] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        self.db_client.put(entity)
        return True


class DBFirestore(object):
    def __init__(self, db_name):
        self.db_client = firestore.Client()
        self.db_name = db_name

    def update_status(self, object_id, status):
        doc_ref = self.db_client.collection(self.db_name).document(object_id)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        doc['status'] = status
        doc['updated_at'] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        doc_ref.update(doc)
        return True


class GGSFileSanitizer(object):
    def __init__(self):
        self.stg_client = storage.Client()
        self.target_bucket_name = os.environ.get('TARGET_BUCKET_NAME')
        self.max_file_size = int(os.environ.get('MAX_FILE_SIZE', 268435456))  # Defaults to 256MB

        self.credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/devstorage.read_write'])
        self.transport = tr_requests.AuthorizedSession(self.credentials)

        Image.MAX_IMAGE_PIXELS = self.max_file_size

    def sanitize(self, data):
        # Only sanitizing files smaller than 0.5GB
        if int(data['size']) > self.max_file_size:
            logging.info(
                f"File '{data['name']}' too big to process (size: {data['size']}, max: {self.max_file_size}), " +
                "skipping sanitizing")
            process_status('failed', data['name'])
            return

        # Only sanitizing files of certain type
        if data['contentType'] not in ['application/pdf', 'image/png', 'image/jpeg']:
            logging.info(
                f"File '{data['name']}' not of type 'application/pdf', 'image/png' or 'image/jpeg', " +
                "skipping sanitizing")
            process_status('failed', data['name'])
            return

        logging.info(f"Starting sanitizing of file '{data['name']}'")

        if data['contentType'] in ['image/jpeg', 'image/png']:
            is_processed = self.process_image(data)
        else:
            is_processed = self.process_pdf(data)

        if is_processed:
            logging.info(f"Finished sanitizing of file '{data['name']}' successfully")
        else:
            process_status('failed', data['name'])

    def process_image(self, data):
        # Setting chunk sizes
        file_size = int(data['size'])
        chunk_size = 10485760 if file_size > 26214400 else 5242880  # 10MB if file > 25MB else 5MB
        current_chunk = 0

        # Setting streams
        stream_down = io.BytesIO()
        stream_up = io.BytesIO()

        try:
            # Creating Download and Upload objects
            download = ChunkedDownload(data['mediaLink'], chunk_size, stream_down)
            upload = ResumableUpload(
                f"https://www.googleapis.com/upload/storage/v1/b/{self.target_bucket_name}/o?uploadType=resumable",
                chunk_size)

            # Initiate upload
            upload.initiate(
                self.transport, stream_up, {'name': data['name']}, data['contentType'],
                total_bytes=file_size, stream_final=False)

            while download.finished is False:
                logging.debug(f"Processing chunk {current_chunk + 1} of {math.ceil((file_size/chunk_size))}")
                response = download.consume_next_chunk(self.transport)

                na = np.array(response.content)
                sanitized_content = na.tobytes()

                stream_up.write(sanitized_content)
                stream_up.seek(current_chunk * chunk_size)

                upload.transmit_next_chunk(self.transport)
                current_chunk += 1
        except Exception as e:
            logging.exception(e)
            return False

        return True

    def process_pdf(self, data):
        # Setting chunk sizes
        file_size = int(data['size'])
        chunk_size = 10485760 if file_size > 26214400 else 5242880  # 10MB if file > 25MB else 5MB
        current_chunk = 0

        # Open temporary file
        temp_file = tempfile.TemporaryFile('wb+')

        # Setting download stream
        stream_down = io.BytesIO()
        download = ChunkedDownload(data['mediaLink'], chunk_size, stream_down)

        try:
            while download.finished is False:
                logging.debug(f"Downloading chunk {current_chunk + 1} of {math.ceil((file_size / chunk_size))}")
                response = download.consume_next_chunk(self.transport)

                temp_file.write(response.content)
                current_chunk += 1
        except Exception as e:
            logging.info(
                f"An exception occurred while downloading file '{data['name']}', skipping sanitizing: {str(e)}")
            return False

        writer = PdfFileWriter()
        try:
            reader = PdfFileReader(temp_file, strict=False)
            writer.appendPagesFromReader(reader)

            writer.removeLinks()
        except utils.PdfReadWarning as e:
            logging.info(
                f"A PDF Read Warning occurred when reading PDF file '{data['name']}', continuing sanitizing: {str(e)}")
            pass
        except Exception as e:
            logging.info(
                f"An exception occurred when reading PDF file '{data['name']}', skipping sanitizing: {str(e)}")
            return False

        # Start file upload
        current_chunk = 0
        stream_up = io.BytesIO()
        writer.write(stream_up)
        stream_up.seek(0)

        del writer
        del reader
        temp_file.close()

        try:
            # Start file upload
            upload = ResumableUpload(
                f"https://www.googleapis.com/upload/storage/v1/b/{self.target_bucket_name}/o?uploadType=resumable",
                chunk_size)

            upload.initiate(
                self.transport, stream_up, {'name': data['name']}, data['contentType'],
                total_bytes=stream_up.getbuffer().nbytes)

            while upload.finished is False:
                logging.debug(
                    f"Uploading chunk {current_chunk + 1} of {math.ceil((stream_up.getbuffer().nbytes / chunk_size))}")
                upload.transmit_next_chunk(self.transport)
                current_chunk += 1
        except Exception as e:
            logging.info(
                f"An exception occurred while uploading file '{data['name']}', skipping sanitizing: {str(e)}")
            return False

        return True


def process_status(status, entity_id):
    if os.environ.get('FILE_DATABASE_TYPE') and os.environ.get('FILE_DATABASE_NAME'):
        db_type = os.environ.get('FILE_DATABASE_TYPE')
        db_name = os.environ.get('FILE_DATABASE_NAME')

        if db_type == 'datastore':
            db_class = DBDatastore(db_name)
        elif db_type == 'firestore':
            db_class = DBFirestore(db_name)
        else:
            logging.error("Function does not have correct configuration to process statuses")
            return False

        status = db_class.update_status(entity_id, status)

        if status:
            logging.info(f"Entity for file '{entity_id}' successfully updated in database '{db_type}/{db_name}'")
        else:
            logging.info(f"Entity for file '{entity_id}' does not exist in database '{db_type}/{db_name}'")
    else:
        logging.debug('Skipping processing of status due to missing configuration')


def gcs_file_sanitizer(data, context):
    logging.debug(context)

    if not os.environ.get('TARGET_BUCKET_NAME'):
        logging.error("Function does not have correct configuration")
        sys.exit(1)

    try:
        GGSFileSanitizer().sanitize(data)
    except MemoryError as error:
        logging.error(error)


if __name__ == '__main__':
    with open('payload_3.json', 'r') as json_file:
        payload = json.load(json_file)

    gcs_file_sanitizer(payload['data'], payload['context'])
