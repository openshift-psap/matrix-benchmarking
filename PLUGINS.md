# Matrix Benchmarking Visualization Plugins

This document provides an overview of all available visualization plugins in the TOPSAIL project. Each project contains specialized visualization modules that handle data processing, analysis, and reporting for different benchmarking scenarios.

## Plugin Architecture

Each visualization plugin follows a consistent structure:
- **models/**: Data models and KPI definitions
- **store/**: Data storage parsers and Prometheus integrations
- **plotting/**: Visualization components and report generators
- **analyze/**: Analysis modules

All plugins implement a `register()` function to register their components with the matrix benchmarking framework.

## Available Visualization Plugins

### Active Projects

#### 1. Container Benchmarking
**Location**: `projects/container_bench/visualizations/benchmark/`
**Purpose**: Benchmarking container performance and resource utilization
**Components**:
- Comparison reports for different container configurations
- Performance metrics visualization
- Resource usage analysis

#### 2. CRC Timing Analysis
**Location**: `projects/crc-timing/visualizations/crc-timing/`
**Purpose**: Analyzing CodeReady Containers startup and operational timing
**Components**:
- Initialization timing reports
- Error analysis and reporting
- Performance metrics tracking

#### 3. Fine-Tuning Performance Analysis
**Location**: `projects/fine_tuning/visualizations/`
**Purpose**: Comprehensive analysis of model fine-tuning performance across different frameworks
**Modules**:
- `fine_tuning/`: Core fine-tuning metrics and analysis
- `fine_tuning_prom/`: Prometheus metrics integration for fine-tuning
- `fms_hf_tuning/`: Foundation Model Stack and HuggingFace tuning analysis
- `fms_prom/`: FMS Prometheus metrics
- `ibm_comparison/`: IBM model comparison reports
- `ilab_prom/`: InstructLab Prometheus metrics
- `ilab_training/`: InstructLab training analysis
- `ray_benchmark/`: Ray framework benchmarking
- `ray_prom/`: Ray Prometheus integration

#### 4. KServe Model Serving
**Location**: `projects/kserve/visualizations/`
**Purpose**: Analysis of KServe model serving performance and scaling
**Modules**:
- `kserve-llm/`: Large Language Model serving analysis
- `kserve-prom/`: KServe Prometheus metrics
- `kserve-scale/`: Scaling performance analysis

#### 5. Mac AI Load Testing
**Location**: `projects/mac_ai/visualizations/llm_load_test/`
**Purpose**: Load testing analysis for Large Language Model inference on Mac systems
**Components**:
- Latency and throughput analysis
- Token processing metrics
- GPU and CPU utilization tracking
- Llama benchmark integration

#### 6. Matrix Benchmarking Helpers
**Location**: `projects/matrix_benchmarking/visualizations/helpers/`
**Purpose**: Shared visualization utilities and common plotting functions
**Components**:
- Common plotting utilities
- Report generation helpers
- Shared data processing functions

#### 7. RHODS Pipelines
**Location**: `projects/pipelines/visualizations/rhods-pipelines/`
**Purpose**: Red Hat OpenShift Data Science Pipelines performance analysis
**Components**:
- Pipeline execution timeline analysis
- Pod-node mapping visualization
- Performance distribution reports
- Resource utilization tracking

#### 8. Skeleton Template
**Location**: `projects/skeleton/visualizations/skeleton/`
**Purpose**: Template and example visualization plugin for new projects
**Components**:
- Basic report structure
- Prometheus integration example
- Error reporting template
- Control plane monitoring examples

### Deprecated Projects

The following projects contain legacy visualization plugins that are no longer actively maintained but may still be referenced:

- `projects/deprecated/busy_cluster/visualizations/`
- `projects/deprecated/codeflare/visualizations/`
- `projects/deprecated/load-aware/visualizations/`
- `projects/deprecated/notebooks/visualizations/`
- `projects/deprecated/scheduler/visualizations/`

## Plugin Registration

Each visualization plugin registers its components through the `register()` function in the main `__init__.py` file. This function typically registers:

- Report generators
- Data parsers
- Prometheus metric collectors
- Analysis modules
- KPI tables and plots
- LTS (Long Term Storage) documentation

## Common Components

Most plugins include these standard components:

### Models
- **KPI Models**: Key Performance Indicator definitions
- **LTS Models**: Long Term Storage schema definitions
- **Data Models**: Pydantic models for data validation

### Store
- **Parsers**: Raw data parsing and transformation
- **Prometheus Integration**: Metrics collection and processing
- **LTS Parser**: Long-term storage data handling

### Plotting
- **Reports**: Dashboard-style comprehensive reports
- **Error Reports**: Error analysis and visualization
- **Metrics Plots**: Individual metric visualizations
- **Comparison Reports**: Side-by-side analysis

### Analysis
- **Statistical Analysis**: Performance trend analysis
- **Regression Detection**: Performance regression identification
- **Anomaly Detection**: Unusual behavior identification

## Usage

To use a visualization plugin:

1. Ensure the plugin is registered in the matrix benchmarking framework
2. Configure the appropriate data sources and metrics
3. Run the visualization generation through the matrix benchmarking CLI
4. Access generated reports through the web interface

## Development

When creating a new visualization plugin:

1. Use the `skeleton` project as a template
2. Follow the standard directory structure
3. Implement the required `register()` function
4. Define appropriate data models
5. Create plotting and analysis components
6. Test with sample data

For more information on developing visualization plugins, refer to the matrix benchmarking framework documentation.