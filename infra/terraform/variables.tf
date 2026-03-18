# ──────────────────────────────────────────────────────────────────────────────
# Sudoku Ultra — Terraform Variables
# ──────────────────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment: dev | staging | prod"
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Must be dev, staging, or prod."
  }
}

variable "project" {
  description = "Project name used as resource prefix"
  type        = string
  default     = "sudoku-ultra"
}

# ── VPC ───────────────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of AZs to use (at least 2 for RDS Multi-AZ)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

# ── EKS ───────────────────────────────────────────────────────────────────────

variable "eks_cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.30"
}

variable "eks_node_instance_types" {
  description = "EC2 instance types for the default node group"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "eks_node_desired" {
  description = "Desired number of worker nodes"
  type        = number
  default     = 3
}

variable "eks_node_min" {
  description = "Minimum number of worker nodes"
  type        = number
  default     = 2
}

variable "eks_node_max" {
  description = "Maximum number of worker nodes"
  type        = number
  default     = 10
}

# ── RDS (PostgreSQL) ──────────────────────────────────────────────────────────

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "sudoku_ultra"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "sudoku"
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL master password (use Vault in production)"
  type        = string
  sensitive   = true
}

variable "db_allocated_storage" {
  description = "Initial storage (GiB) for RDS"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum auto-scaled storage (GiB) for RDS"
  type        = number
  default     = 100
}

# ── ElastiCache (Redis) ───────────────────────────────────────────────────────

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  description = "Number of cache nodes (1 = standalone, >1 = cluster)"
  type        = number
  default     = 1
}

# ── ECR ───────────────────────────────────────────────────────────────────────

variable "ecr_services" {
  description = "List of service names for ECR repository creation"
  type        = list(string)
  default     = ["game-service", "multiplayer", "ml-service", "notifications"]
}

variable "ecr_image_retention_count" {
  description = "Number of images to keep per ECR repository"
  type        = number
  default     = 20
}
