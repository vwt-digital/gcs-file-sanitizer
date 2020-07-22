# GCS File Sanitizer

A Google Cloud Function to sanitize Google Cloud Storage files and move them towards a GCS Bucket. 

When a file is upload towards the trigger bucket, the function will first check if the file is valid for sanitizing. 
This part will check if the file is not bigger than the specified `MAX_FILE_SIZE` (see [Deployment to GCP](#deployment-to-gcp))
and if it has a supported content-type (see [Supported Content Types](#supported-content-types)). 

After successfully checking the file will be parsed and sanitized by different functions optimized for each content-type,
where after the file will be uploaded towards the specified target bucket (see [Deployment to GCP](#deployment-to-gcp)).

### Supported Content Types
This functions supports the following content types to be sanitized:
- `application/pdf`
- `image/jpeg`
- `image/png`

### Memory limit
To ensure each file will be sanitized and the Cloud Function won't run out of memory, the function has the option to limit
the size of the files that will be processed. Within the deployment the environment variable `MAX_FILE_SIZE` can be used
to set this maximum file size in bytes (see [Deployment to GCP](#deployment-to-gcp)). The function defaults to a 
standard maximum size of `536870912 bytes / 512MB`.

Make sure when setting this file size, the [Cloud Function memory](https://cloud.google.com/sdk/gcloud/reference/functions/deploy#--memory)
will be enough to process these sizes. Because the function first retrieves the original file and then creates a new parsed file, 
the function need to support `2 x MAX_FILE_SIZE` specified.

> E.g. The standard maximum file size will accept files not bigger than `512MB`, therefor the function must be set at a memory of `1024MB` 

### Deployment to GCP
An example of a Google Cloud Build step is defined within the [cloudbuild.example.yaml](functions/gcs-file-sanitizer/cloudbuild.example.yaml).
Within this example, the variables below need to be updated to your needs:
- `--trigger-resource` `[string]`: The GCS Bucket name the trigger has to execute to;
- `--memory` `[string]`: The [Cloud Function memory](https://cloud.google.com/sdk/gcloud/reference/functions/deploy#--memory) memory size.
- `TARGET-BUCKET-NAME` `[string]`: The GCS Bucket name the sanitized files will be moved to;
- `MAX_FILE_SIZE` `[integer]`: The maximum file size to be processed in bytes, defaults to `536870912 bytes / 512MB`;

### License
This function is licensed under the [GPL-3](https://www.gnu.org/licenses/gpl-3.0.en.html) License
