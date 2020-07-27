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
standard maximum size of `268435456 bytes / 256MB`.

Make sure when setting this file size, the [Cloud Function memory](https://cloud.google.com/sdk/gcloud/reference/functions/deploy#--memory)
will be enough to process these sizes. Because the function first retrieves the original file and then creates a new parsed file, 
the function need to support minimal `3 x MAX_FILE_SIZE` specified. This only applies when sanitizing PDF-files. When using images,
the sanitizing is done in chunks of max 10MB.

> E.g. The standard maximum file size will accept files not bigger than `256MB`, therefore the function must be set at a minimal memory of `1024MB` 

### Status processing
When using this function it is possible to report when a file failed to process with declaring two environment 
variables: `FILE_DATABASE_TYPE` and `FILE_DATABASE_NAME` (see [Deployment to GCP](#deployment-to-gcp)). With these 
variables a file entity will be retrieved and updated with a status change to `failed`. This can help you to follow 
up on files that aren't sanitized.

The following fields will be updated within the entity:
- `status` `[string]`: The status of the current file, defaults to `failed`;
- `updated_at` `[string]`: The current timestamp in format `2020-01-01T12:00:00.000Z`.

This function supports two GCP databases and has to be set by the environment variable `FILE_DATABASE_TYPE`:
- `datastore`: [Google Cloud Datastore](https://cloud.google.com/datastore/docs)
- `firestore`: [Google Cloud Firestore](https://cloud.google.com/firestore/docs)  

### Deployment to GCP
An example of a Google Cloud Build step is defined within the [cloudbuild.example.yaml](functions/gcs-file-sanitizer/cloudbuild.example.yaml).
Within this example, the variables below need to be updated to your needs:
- `--trigger-resource` `[string]`: The GCS Bucket name the trigger has to execute to;
- `--memory` `[string]`: The [Cloud Function memory](https://cloud.google.com/sdk/gcloud/reference/functions/deploy#--memory) memory size.
- `TARGET-BUCKET-NAME` `[string]`: The GCS Bucket name the sanitized files will be moved to;
- `MAX_FILE_SIZE` `[integer]`: The maximum file size to be processed in bytes, defaults to `268435456 bytes / 256MB`;
- `FILE_DATABASE_TYPE` `[string]`: The GCP Database type (see [Status processing](#status-processing));
- `FILE_DATABASE_NAME` `[string]`: The GCP Database Table name (see [Status processing](#status-processing)).

### License
This function is licensed under the [GPL-3](https://www.gnu.org/licenses/gpl-3.0.en.html) License
