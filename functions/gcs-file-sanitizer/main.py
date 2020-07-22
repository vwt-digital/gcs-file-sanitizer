import sys
import logging
import json
import tempfile
import os
import mimetypes
import xmltodict
import defusedxml
import numpy as np

from google.cloud import storage
from PIL import Image
from PyPDF2 import PdfFileReader, PdfFileWriter, utils

from modules.pdfid import PDFiD
from modules.gcs_stream_to_blob import GCSObjectStreamUpload

logging.getLogger().setLevel(logging.INFO)


class GGSFileSanitizer(object):
    def __init__(self):
        self.stg_client = storage.Client()
        self.target_bucket_name = os.environ.get('TARGET_BUCKET_NAME')
        self.max_file_size = int(os.environ.get('MAX_FILE_SIZE', 536870912))  # Defaults to 512MB

        Image.MAX_IMAGE_PIXELS = self.max_file_size

    def sanitize(self, data):
        # Only sanitizing files smaller than 0.5GB
        if int(data['size']) > self.max_file_size:
            logging.info(
                f"File '{data['name']}' too big to process (size: {data['size']}, max: {self.max_file_size}), " +
                "skipping sanitizing")
            sys.exit()

        # Only sanitizing files of certain type
        if data['contentType'] not in ['application/pdf', 'image/png', 'image/jpeg']:
            logging.info(
                f"File '{data['name']}' not of type 'application/pdf', 'image/png' or 'image/jpeg', " +
                "skipping sanitizing")
            sys.exit()

        source_bucket = self.stg_client.get_bucket(data['bucket'])
        source_blob = source_bucket.blob(data['name'])

        # Check if file exists in defined bucket
        if not source_blob.exists():
            logging.info(f"File '{data['name']}' does not exist in bucket '{data['bucket']}', skipping sanitizing")
            sys.exit()

        logging.info(f"Starting sanitizing of file '{data['name']}'")

        # Write file contents to temporary file
        temp_file_save = None
        temp_file = tempfile.NamedTemporaryFile(
            mode='w+b', delete=False, suffix=mimetypes.guess_extension(data['contentType']))
        source_blob.download_to_filename(temp_file.name)

        try:
            if data['contentType'] == 'application/pdf':
                temp_file_save = sanitize_pdf_file(data, temp_file)
            elif data['contentType'] == 'image/jpeg':
                temp_file_save = sanitize_jpeg_file(temp_file)
            elif data['contentType'] == 'image/png':
                temp_file_save = sanitize_png_file(temp_file)
        except Exception as e:
            temp_file.close()
            os.unlink(temp_file.name)  # Unlink

            logging.info(f"An exception occurred when sanitizing file '{data['name']}', skipping sanitizing: {str(e)}")
            sys.exit()

        # Unlink original temp file
        temp_file.close()
        os.unlink(temp_file.name)

        if temp_file_save:
            self.write_stream_to_blob(
                path=data['name'], content=open(temp_file_save.name, 'rb'), content_type=data['contentType'])
            os.unlink(temp_file_save.name)  # Unlink

            logging.info(
                f"File '{data['name']}' has been successfully sanitized and " +
                f"moved to bucket '{self.target_bucket_name}'")
        else:
            logging.info(f"File '{data['name']}' has been unsuccessfully sanitized")

    def write_stream_to_blob(self, path, content, content_type):
        try:
            with GCSObjectStreamUpload(
                    client=self.stg_client, bucket_name=self.target_bucket_name, blob_name=path,
                    content_type=content_type) as f, content as fp:
                buffer = fp.read(1024)
                while buffer:
                    f.write(buffer)
                    buffer = fp.read(1024)
        except Exception as e:
            logging.info(f"An exception occurred when moving file '{path}', skipping moving: {str(e)}")
            sys.exit()


def sanitize_pdf_file(data, temp_file):
    defusedxml.defuse_stdlib()
    xml_keywords = xmltodict.parse(PDFiD(temp_file.name).toxml("UTF-8")).get('PDFiD', {}).get('Keywords', {})

    if xml_keywords:
        logging.info(f"Found {len(xml_keywords.get('Keyword'))} obfuscations for '{data['name']}', starting sanitizing")

        # Remove links from PDF file
        writer = PdfFileWriter()
        try:
            reader = PdfFileReader(temp_file, strict=False)
            [writer.addPage(reader.getPage(i)) for i in range(0, reader.getNumPages())]
            writer.removeLinks()
        except utils.PdfReadWarning as e:
            logging.info(
                f"An exception occurred when reading PDF file '{data['name']}', continuing sanitizing: {str(e)}")
            pass

        # Unlink original temp file
        temp_file.close()
        os.unlink(temp_file.name)

        with tempfile.NamedTemporaryFile(mode='w+b', delete=False) as temp_flat_file:
            writer.write(temp_flat_file)
            temp_flat_file.close()

        return temp_flat_file
    else:
        logging.info(f"Found no obfuscations for '{data['name']}', skipping sanitizing")
        temp_file.close()
        return temp_file


def sanitize_jpeg_file(temp_file):
    # Load image
    im = Image.open(temp_file.name)

    # Convert to format that cannot store IPTC/EXIF or comments, i.e. Numpy array
    na = np.array(im)

    # Create new image from the Numpy array and save
    temp_file_sanitized = tempfile.NamedTemporaryFile(mode='w+b', delete=False)
    Image.fromarray(na).save(temp_file_sanitized.name, format='jpeg')

    # Return temporary file
    temp_file_sanitized.close()
    return temp_file_sanitized


def sanitize_png_file(temp_file):
    # Load image
    im = Image.open(temp_file.name)

    # Convert to format that cannot store IPTC/EXIF or comments, i.e. Numpy array
    na = np.array(im)

    # Create new image from the Numpy array
    result = Image.fromarray(na)

    # Copy forward the palette, if any
    palette = im.getpalette()
    if palette is not None:
        result.putpalette(palette)

    # Save result
    temp_file_sanitized = tempfile.NamedTemporaryFile(mode='w+b', delete=False)
    result.save(temp_file_sanitized, format='png')

    # Return temporary file
    temp_file_sanitized.close()
    return temp_file_sanitized


def gcs_file_sanitizer(data, context):
    if not os.environ.get('TARGET_BUCKET_NAME'):
        logging.error("Function does not have correct configuration")
        sys.exit(1)

    logging.debug(context)

    GGSFileSanitizer().sanitize(data)


if __name__ == '__main__':
    with open('payload.json', 'r') as json_file:
        payload = json.load(json_file)

    gcs_file_sanitizer(payload['data'], payload['context'])
