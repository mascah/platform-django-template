Deployment on AWS
=================

.. index:: AWS, ECS, EKS, Terraform, Terragrunt, Infrastructure as Code

Overview
--------

This guide documents patterns and approaches for deploying Django + Turborepo monorepos to AWS using Terraform and Terragrunt. Rather than providing ready-to-use configurations (which are on the :doc:`/6-about/roadmap`), this guide establishes architectural patterns you can implement in your project.

**Infrastructure as Code Philosophy**

Embedding infrastructure definitions in your monorepo provides several benefits:

- **Co-location**: Infrastructure changes are reviewed alongside application code
- **Atomic changes**: A single PR can update both application and infrastructure
- **Single source of truth**: No drift between documentation and actual infrastructure
- **Version history**: Full audit trail of infrastructure evolution

.. note::

    This guide assumes familiarity with Terraform concepts. For Terraform basics, see the `official Terraform documentation <https://developer.hashicorp.com/terraform/docs>`_.

Monorepo Infrastructure Layout
------------------------------

Add an ``infrastructure/`` directory at the repository root alongside your existing ``apps/``, ``packages/``, and Django directories:

.. code-block:: text

    my_project/
    ├── apps/                    # Frontend applications
    ├── packages/                # Shared frontend packages
    ├── config/                  # Django settings
    ├── my_project/              # Django modular monolith
    ├── docker/                  # Docker configurations
    └── infrastructure/          # Terraform/Terragrunt
        ├── terragrunt.hcl       # Root config (backend, providers)
        ├── modules/             # Custom Terraform modules
        │   ├── django-app/      # ECS task + service + ALB target
        │   ├── celery-worker/   # Celery worker ECS service
        │   └── frontend-cdn/    # CloudFront + S3 for frontends
        └── environments/
            ├── _env/            # Shared environment configs
            │   ├── vpc.hcl
            │   ├── rds.hcl
            │   └── ecs.hcl
            ├── dev/
            │   ├── env.hcl      # Environment-specific variables
            │   ├── vpc/
            │   ├── rds/
            │   └── ecs/
            ├── staging/
            └── production/

The separation between ``modules/`` (reusable components) and ``environments/`` (deployment configurations) keeps infrastructure DRY while allowing environment-specific customization.

Choosing Between ECS and EKS
----------------------------

AWS offers two primary container orchestration services. Choose based on your team's needs:

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Factor
     - ECS (Elastic Container Service)
     - EKS (Elastic Kubernetes Service)
   * - Complexity
     - Lower, AWS-native concepts
     - Higher, full Kubernetes ecosystem
   * - Learning curve
     - Minimal if familiar with AWS
     - Requires Kubernetes expertise
   * - Team size
     - Small to medium teams
     - Medium to large teams
   * - Portability
     - AWS-locked
     - Multi-cloud capable
   * - Cost (small scale)
     - Lower with Fargate
     - Higher (control plane fee)
   * - Ecosystem
     - AWS-native tooling
     - Rich Kubernetes ecosystem

When to Choose ECS
^^^^^^^^^^^^^^^^^^

- AWS-first teams without multi-cloud requirements
- Simpler operational model preferred
- Fargate for serverless container management
- Smaller teams without dedicated platform engineers
- Faster time-to-production for AWS workloads

When to Choose EKS
^^^^^^^^^^^^^^^^^^

- Multi-cloud or hybrid-cloud strategy planned
- Team already has Kubernetes expertise
- Need for advanced scheduling, service mesh, or GitOps workflows
- Plan to use Helm charts extensively
- Want portability to other Kubernetes environments

Core AWS Resources
------------------

A production Django deployment requires several AWS services working together.

Networking (VPC)
^^^^^^^^^^^^^^^^

Create a VPC with public and private subnets across multiple availability zones:

.. code-block:: hcl

    module "vpc" {
      source  = "terraform-aws-modules/vpc/aws"
      version = "~> 5.0"

      name = "${var.project}-${var.environment}"
      cidr = "10.0.0.0/16"

      azs             = ["us-east-1a", "us-east-1b", "us-east-1c"]
      private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
      public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

      enable_nat_gateway = true
      single_nat_gateway = var.environment != "production"
    }

- **Public subnets**: ALB, NAT Gateways
- **Private subnets**: ECS tasks, RDS, ElastiCache
- **NAT Gateway**: Single for dev/staging, multi-AZ for production

Database (RDS)
^^^^^^^^^^^^^^

PostgreSQL on RDS matches your local Docker PostgreSQL setup:

.. code-block:: hcl

    module "rds" {
      source  = "terraform-aws-modules/rds/aws"
      version = "~> 6.0"

      identifier = "${var.project}-${var.environment}"
      engine     = "postgres"
      engine_version = "18"
      family     = "postgres18"

      instance_class    = var.environment == "production" ? "db.r6g.large" : "db.t4g.micro"
      allocated_storage = 20
      multi_az          = var.environment == "production"

      db_subnet_group_name   = module.vpc.database_subnet_group_name
      vpc_security_group_ids = [aws_security_group.rds.id]
    }

- Enable Multi-AZ for production high availability
- Configure automated backups and encryption at rest
- Use parameter groups for Django-optimized settings

Cache and Message Broker (ElastiCache)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Redis serves as both Celery broker and Django cache backend:

- **Cluster mode disabled** for simpler operations at small scale
- **Cluster mode enabled** for high-throughput production workloads
- Place in private subnets with security group restricting access to ECS tasks

Object Storage (S3)
^^^^^^^^^^^^^^^^^^^

.. code-block:: hcl

    module "s3_media" {
      source  = "terraform-aws-modules/s3-bucket/aws"
      version = "~> 4.0"

      bucket = "${var.project}-${var.environment}-media"

      versioning = { enabled = true }

      cors_rule = [{
        allowed_headers = ["*"]
        allowed_methods = ["GET", "PUT", "POST"]
        allowed_origins = var.allowed_origins
        max_age_seconds = 3600
      }]
    }

- **Static files bucket**: For ``collectstatic`` output (alternative to Whitenoise)
- **Media files bucket**: User uploads with appropriate CORS configuration
- **CloudFront distribution**: Optional CDN for static and media assets

Container Registry (ECR)
^^^^^^^^^^^^^^^^^^^^^^^^

Store your production Docker images in ECR:

- Create repository for Django production image
- Configure lifecycle policies to clean old images
- Grant ECS task execution role pull permissions

Secrets Management
^^^^^^^^^^^^^^^^^^

Use AWS Secrets Manager for sensitive configuration:

- ``DJANGO_SECRET_KEY``
- Database credentials
- Third-party API keys

ECS and EKS both support native Secrets Manager integration for injecting secrets into containers at runtime.

Observability
^^^^^^^^^^^^^

AWS provides native observability through CloudWatch:

- **CloudWatch Logs**: Container stdout/stderr with JSON structured logging
- **CloudWatch Metrics**: Container and application metrics
- **X-Ray**: Distributed tracing across services

For detailed observability patterns including OpenTelemetry integration, see :doc:`/4-guides/observability-logging`.

Terraform Modules Approach
--------------------------

Use well-maintained community modules where appropriate, and create custom modules for application-specific patterns.

Recommended Community Modules
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The `terraform-aws-modules <https://github.com/terraform-aws-modules>`_ organization (maintained by Anton Babenko) provides battle-tested modules:

- ``terraform-aws-modules/vpc/aws`` - VPC with subnets, NAT, routing
- ``terraform-aws-modules/rds/aws`` - RDS instances and clusters
- ``terraform-aws-modules/s3-bucket/aws`` - S3 buckets with policies
- ``terraform-aws-modules/ecs/aws`` - ECS clusters and services
- ``terraform-aws-modules/eks/aws`` - EKS clusters and node groups
- ``terraform-aws-modules/alb/aws`` - Application Load Balancers

Custom Application Modules
^^^^^^^^^^^^^^^^^^^^^^^^^^

Create custom modules in ``infrastructure/modules/`` for patterns specific to your Django application:

- **django-app**: Wraps ECS task definition, service, ALB target group, and auto-scaling
- **celery-worker**: Configures Celery worker services with queue-specific scaling
- **frontend-cdn**: Sets up CloudFront distribution with S3 origin for frontend apps

Terragrunt for Environment Management
-------------------------------------

Terragrunt provides DRY configurations and dependency management across environments.

Directory Structure Pattern
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

    infrastructure/
    ├── terragrunt.hcl              # Root config
    └── environments/
        ├── _env/                   # Shared configs (included by environments)
        │   ├── vpc.hcl
        │   ├── rds.hcl
        │   └── ecs.hcl
        ├── dev/
        │   ├── env.hcl             # environment = "dev", instance sizes, etc.
        │   ├── vpc/terragrunt.hcl
        │   ├── rds/terragrunt.hcl
        │   └── ecs/terragrunt.hcl
        ├── staging/
        └── production/

Each environment includes shared configs and overrides environment-specific variables.

Dependency Management
^^^^^^^^^^^^^^^^^^^^^

Use Terragrunt ``dependency`` blocks to pass outputs between stacks:

.. code-block:: hcl

    # environments/dev/ecs/terragrunt.hcl
    dependency "vpc" {
      config_path = "../vpc"
    }

    dependency "rds" {
      config_path = "../rds"
    }

    inputs = {
      vpc_id          = dependency.vpc.outputs.vpc_id
      private_subnets = dependency.vpc.outputs.private_subnets
      database_url    = dependency.rds.outputs.connection_string
    }

Remote State Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^

Configure S3 backend with DynamoDB locking in the root ``terragrunt.hcl``:

.. code-block:: hcl

    # infrastructure/terragrunt.hcl
    remote_state {
      backend = "s3"
      config = {
        bucket         = "my-project-terraform-state"
        key            = "${path_relative_to_include()}/terraform.tfstate"
        region         = "us-east-1"
        encrypt        = true
        dynamodb_table = "terraform-locks"
      }
    }

ECS Deployment Pattern
----------------------

ECS with Fargate provides serverless container orchestration.

Architecture Overview
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

    Internet
        │
        ▼
    ALB (Application Load Balancer)
        │
        ├── /api/* ──────► ECS Django Service (Gunicorn/Uvicorn)
        │                       │
        │                       ├── Task 1
        │                       ├── Task 2
        │                       └── Task N (auto-scaled)
        │
        └── /* ──────────► CloudFront ──► S3 (Frontend apps)

    Private Subnets
        │
        ├── ECS Celery Worker Service (if use_celery=y)
        │       └── Tasks scaled by queue depth
        │
        └── ECS Celery Beat Service (single task)

    Data Layer (Private Subnets)
        │
        ├── RDS PostgreSQL (Multi-AZ in production)
        └── ElastiCache Redis

ECS Task Definition
^^^^^^^^^^^^^^^^^^^

Map your production Dockerfile to an ECS task definition:

.. code-block:: hcl

    resource "aws_ecs_task_definition" "django" {
      family                   = "${var.project}-django"
      requires_compatibilities = ["FARGATE"]
      network_mode             = "awsvpc"
      cpu                      = 512
      memory                   = 1024

      container_definitions = jsonencode([{
        name  = "django"
        image = "${aws_ecr_repository.django.repository_url}:${var.image_tag}"
        portMappings = [{ containerPort = 8000 }]
        secrets = [
          { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.db.arn }
        ]
        logConfiguration = {
          logDriver = "awslogs"
          options   = { "awslogs-group" = "/ecs/${var.project}" }
        }
      }])
    }

ECS Service Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^

Configure the service with auto-scaling and load balancer integration:

- **Desired count**: Start with 2 for high availability
- **Deployment**: Rolling update with minimum healthy percent
- **Auto-scaling**: Scale on CPU, memory, or custom CloudWatch metrics
- **Health check**: ALB health check on Django health endpoint

Celery Workers on ECS
^^^^^^^^^^^^^^^^^^^^^

Deploy Celery as separate ECS services:

- **Worker service**: Scales based on SQS/Redis queue depth
- **Beat service**: Single task (``desired_count = 1``) for scheduler
- **Multiple queues**: Create separate services per queue for independent scaling

See :doc:`/4-guides/production-patterns` for Celery configuration patterns.

EKS Deployment Pattern
----------------------

EKS provides managed Kubernetes for teams with Kubernetes expertise.

Architecture Overview
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

    Internet
        │
        ▼
    AWS Load Balancer Controller (Ingress)
        │
        ├── /api/* ──────► Django Deployment (Pods)
        │                       │
        │                       ├── Pod 1
        │                       ├── Pod 2
        │                       └── Pod N (HPA scaled)
        │
        └── /* ──────────► Frontend Deployment or external CDN

    Kubernetes Cluster
        │
        ├── Celery Worker Deployment
        │       └── Pods scaled by KEDA or HPA
        │
        └── Celery Beat Deployment (replicas: 1)

    AWS Managed Services
        │
        ├── RDS PostgreSQL
        └── ElastiCache Redis

Kubernetes Resources
^^^^^^^^^^^^^^^^^^^^

Core resources for Django on Kubernetes:

- **Namespace**: Isolate per environment (``dev``, ``staging``, ``production``)
- **Deployment**: Django pods with readiness/liveness probes
- **Service**: ClusterIP for internal communication
- **Ingress**: AWS ALB Ingress Controller for external traffic
- **ConfigMap**: Non-sensitive configuration
- **External Secrets**: Sync AWS Secrets Manager to Kubernetes secrets
- **HorizontalPodAutoscaler**: Scale on CPU/memory metrics

EKS Cluster Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^

- **Managed node groups**: Simplest approach, AWS handles node lifecycle
- **Fargate profiles**: Serverless pods for specific namespaces
- **IRSA (IAM Roles for Service Accounts)**: Fine-grained AWS permissions per pod
- **VPC CNI**: Native AWS networking for pods

Future: Helm Charts
^^^^^^^^^^^^^^^^^^^

Helm charts enable templated, versioned Kubernetes deployments. Planned features include:

- Django application chart with Deployment, Service, Ingress
- Celery worker and beat sub-charts
- Values files for environment configuration
- Integration with External Secrets Operator
- ArgoCD/Flux compatibility for GitOps workflows

.. note::

    Helm chart templates are on the :doc:`/6-about/roadmap`. The patterns described here can be implemented with raw Kubernetes manifests or Kustomize until charts are available.

CI/CD Patterns
--------------

Integrate infrastructure and application deployment with GitHub Actions.

ECS Deployment Workflow
^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

    # .github/workflows/deploy-ecs.yml
    name: Deploy to ECS

    on:
      push:
        branches: [main]

    jobs:
      deploy:
        runs-on: ubuntu-latest
        steps:
          - uses: aws-actions/configure-aws-credentials@v4
            with:
              role-to-assume: ${{ secrets.AWS_ROLE_ARN }}

          - uses: aws-actions/amazon-ecr-login@v2

          - name: Build and push image
            run: |
              docker build -t $ECR_REPO:${{ github.sha }} .
              docker push $ECR_REPO:${{ github.sha }}

          - name: Run migrations
            run: |
              aws ecs run-task --cluster $CLUSTER \
                --task-definition $TASK_DEF \
                --overrides '{"containerOverrides":[{"name":"django","command":["python","manage.py","migrate"]}]}'

          - name: Deploy service
            run: |
              aws ecs update-service --cluster $CLUSTER \
                --service $SERVICE --force-new-deployment

Terraform Workflow
^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

    # .github/workflows/terraform.yml
    name: Terraform

    on:
      pull_request:
        paths: ['infrastructure/**']
      push:
        branches: [main]
        paths: ['infrastructure/**']

    jobs:
      terraform:
        runs-on: ubuntu-latest
        steps:
          - name: Terraform Plan
            if: github.event_name == 'pull_request'
            run: terragrunt run-all plan

          - name: Terraform Apply
            if: github.ref == 'refs/heads/main'
            run: terragrunt run-all apply -auto-approve

Database Migrations
^^^^^^^^^^^^^^^^^^^

Run migrations before deploying new application versions:

- **ECS**: Use ``aws ecs run-task`` with command override
- **EKS**: Create a Kubernetes Job or use init container

For zero-downtime migration patterns, see :doc:`/4-guides/production-patterns`.

Secrets and Configuration
-------------------------

Separate sensitive secrets from application configuration.

AWS Secrets Manager
^^^^^^^^^^^^^^^^^^^

Store sensitive values that should never appear in logs or version control:

- ``DJANGO_SECRET_KEY``
- ``DATABASE_URL`` (with password)
- Third-party API credentials (Stripe, SendGrid, etc.)

Both ECS and EKS support native integration:

- **ECS**: Reference secrets in task definition ``secrets`` block
- **EKS**: Use External Secrets Operator to sync to Kubernetes secrets

AWS Systems Manager Parameter Store
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Store non-sensitive configuration that varies by environment:

- ``DJANGO_ALLOWED_HOSTS``
- ``CELERY_BROKER_URL`` (without password in path)
- Feature flags and environment identifiers

Parameter Store is lower cost than Secrets Manager for high-read scenarios.

See Also
--------

- :doc:`/4-guides/observability-logging` - CloudWatch integration and structured logging
- :doc:`/4-guides/production-patterns` - Zero-downtime migrations and feature flags
- :doc:`/1-getting-started/configuration` - Environment variable patterns
- :doc:`deployment-on-heroku` - Alternative: simpler Heroku deployment
- `terraform-aws-modules <https://github.com/terraform-aws-modules>`_ - Community Terraform modules
- `Terragrunt Documentation <https://terragrunt.gruntwork.io/docs/>`_ - Terragrunt guides and reference
