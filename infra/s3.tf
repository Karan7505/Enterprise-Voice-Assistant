# S3 audio store — per-user keys user-{id}/{filename}, 90-day expiration
# (blueprint Change 4). Audio is regenerable, so the lifecycle rule is the
# only retention mechanism; no versioning needed for v1.

resource "aws_s3_bucket" "audio" {
  bucket = "${var.project}-${var.environment}-assistant-audio"

  tags = { Name = "${var.project}-${var.environment}-assistant-audio" }
}

resource "aws_s3_bucket_public_access_block" "audio" {
  bucket = aws_s3_bucket.audio.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id

  rule {
    id     = "expire-audio"
    status = "Enabled"

    # Empty filter = all objects in the bucket.
    filter {}

    expiration {
      days = 90
    }
  }
}
