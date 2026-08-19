# Troubleshooting

## S3 says the notification destination cannot be validated

S3 validates the SQS destination while the bucket is being configured. Confirm that:

- the SQS queue exists
- the queue policy allows `s3.amazonaws.com` to call `sqs:SendMessage`
- the `aws:SourceArn` matches the upload bucket name
- the `aws:SourceAccount` is the account deploying the stack

The SAM template makes the upload bucket depend on the queue policy so the permission exists before S3 configures the notification.

## The stack fails because the bucket name already exists

S3 bucket names are globally unique. Deploy again with unique values for `UploadBucketName` and `ProcessedBucketName`.

## An upload never appears in the processed bucket

Check in this order:

1. confirm the object exists in the upload bucket
2. inspect SQS queue depth
3. inspect the Lambda log stream in CloudWatch
4. check whether the message moved to the DLQ
5. confirm the file extension is `.jpg`, `.jpeg`, or `.png`

Unsupported extensions are deliberately acknowledged and ignored.

## The same image appears to process more than once

Asynchronous AWS events can be delivered more than once. The processor skips a repeat when the deterministic output exists with the same source ETag metadata.

A race can still cause duplicate work if two matching events execute before the first result becomes visible. If stronger coordination matters, add a state store with conditional writes and document the new failure modes.

## Images keep landing in the DLQ

Inspect the Lambda logs and the source object. Common causes include:

- corrupt image content
- payload larger than the configured 10 MiB limit
- S3 access failure
- invalid processor configuration
- a library/runtime packaging problem

After fixing the cause, redrive messages deliberately rather than deleting the DLQ blindly.

## Lambda times out

The function timeout is 30 seconds and the SQS visibility timeout is 180 seconds. Very large or complex images may still exceed the function's practical processing budget.

Consider reducing accepted image size, increasing memory, profiling processing time, or splitting workflows based on input size. Do not simply raise timeouts without understanding the cost and retry impact.

## `sam build` fails while installing Pillow

Use a supported Python 3.12 environment and a current AWS SAM CLI. If your local operating system cannot produce a Lambda-compatible dependency build, use SAM's container build option:

```bash
sam build --use-container
```

Docker is required for that mode.

## `sam delete` cannot remove the stack

CloudFormation cannot delete non-empty S3 buckets. Empty both buckets first:

```bash
aws s3 rm s3://YOUR_UPLOAD_BUCKET --recursive
aws s3 rm s3://YOUR_PROCESSED_BUCKET --recursive
sam delete
```
