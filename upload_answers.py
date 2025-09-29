#!/usr/bin/env python3
"""
Upload script for Decoding Biology Hackathon Platform

This script validates and uploads JSONL answer files to the S3 bucket.
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import List, Tuple
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import argparse
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# S3 Configuration
S3_BUCKET = "709747128509-hackathon-results"
S3_PREFIX = "/"

def validate_jsonl_file(file_path: Path) -> Tuple[bool, List[str]]:
    """
    Validate the JSONL file format and content.
    
    Args:
        file_path: Path to the JSONL file
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    if not file_path.exists():
        errors.append(f"File not found: {file_path}")
        return False, errors
    
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        errors.append(f"Error reading file: {e}")
        return False, errors
    
    if not lines:
        errors.append("File is empty")
        return False, errors
    
    seen_questions = set()
    # Validate each line
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
            
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"Line {i}: Invalid JSON - {e}")
            continue

        if data['question']+data['options'] in seen_questions:
            errors.append(f"Line {i}: Question already seen, only the first instance of each question is evaluated")
            continue

        # Check required fields
        required_fields = ['question', 'options', 'answer_letter']
        for field in required_fields:
            if field not in data:
                errors.append(f"Line {i}: Missing required field '{field}'")
        
        # Validate answer_letter format
        if 'answer_letter' in data:
            answer_letter = data['answer_letter']
            if not isinstance(answer_letter, str):
                errors.append(f"Line {i}: answer_letter must be a string")
            elif not re.match(r'[ABCDE]', answer_letter):
                errors.append(f"Line {i}: answer_letter must be in format [A|B|C|D|E], got: {answer_letter}")

        seen_questions.add(data['question']+data['options'])
    
    return len(errors) == 0, errors

def upload_to_s3(file_path: Path, team_name: str = None, tag: str = None) -> bool:
    """
    Upload the JSONL file to S3.
    
    Args:
        file_path: Path to the JSONL file
        team_name: Team name for the submission (required)
        tag: Optional tag to distinguish different submissions (e.g., model name)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Initialize S3 client
        s3_client = boto3.client('s3')
        
        # Team name is required
        if not team_name:
            logger.error("Team name is required for submission")
            return False
        
        # Automatically uppercase the first letter of the team name
        team_name = team_name[0].upper() + team_name[1:] if team_name else team_name
        
        # Generate S3 key with team-based path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_team_name = re.sub(r'[^a-zA-Z0-9_-]', '_', team_name)
        
        if tag:
            # Sanitize tag for S3 key
            safe_tag = re.sub(r'[^a-zA-Z0-9_-]', '_', tag)
            s3_key = f"{S3_PREFIX}{safe_team_name}/{safe_tag}_{timestamp}.jsonl"
        else:
            s3_key = f"{S3_PREFIX}{safe_team_name}/submission_{timestamp}.jsonl"
        
        # Upload file
        logger.info(f"Uploading {file_path} to s3://{S3_BUCKET}/{s3_key}")
        
        s3_client.upload_file(
            str(file_path),
            S3_BUCKET,
            s3_key,
            ExtraArgs={
                'ContentType': 'application/json',
                'Metadata': {
                    'team_name': team_name,
                    'tag': tag or 'default',
                    'submission_time': timestamp,
                    'file_type': 'hackathon_answers'
                }
            }
        )
        
        logger.info(f"Successfully uploaded to s3://{S3_BUCKET}/{s3_key}")
        return True
        
    except NoCredentialsError:
        logger.error("AWS credentials not found. Please configure your AWS credentials.")
        return False
    except ClientError as e:
        logger.error(f"AWS error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Upload hackathon answers to S3')
    parser.add_argument('file', help='Path to the JSONL file to upload')
    parser.add_argument('--team-name', required=True, help='Team name for the submission (required)')
    parser.add_argument('--tag', help='Optional tag to distinguish different submissions (e.g., model name)')
    parser.add_argument('--validate-only', action='store_true', help='Only validate the file, do not upload')
    
    args = parser.parse_args()
    
    file_path = Path(args.file)
    
    # Validate file
    logger.info(f"Validating file: {file_path}")
    is_valid, errors = validate_jsonl_file(file_path)
    
    if not is_valid:
        logger.error("File validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        sys.exit(1)
    
    logger.info("✓ File validation passed")
    
    if args.validate_only:
        print("✓ File is valid and ready for upload")
        sys.exit(0)
    
    # Upload file
    success = upload_to_s3(file_path, args.team_name, args.tag)
    
    if success:
        print("✓ Upload successful!")
        print(f"  File: {file_path}")
        print(f"  Bucket: s3://{S3_BUCKET}")
        print(f"  Team: {args.team_name}")
        if args.tag:
            print(f"  Tag: {args.tag}")
    else:
        print("✗ Upload failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
