# Web Crawler Project

This project implements sequential, multi-threaded, and MPI-based distributed web crawlers for the **Parallel and Distributed Computing** course assignment. It includes an analysis script (`analyze.py`) to compare the performance of sequential and multi-threaded crawlers, generating visualizations and metrics for evaluation.

## Features

- **Sequential Crawler**: A single-threaded crawler that fetches and extracts data sequentially.
- **Multi-threaded Crawler**: A parallel crawler using Python's `ThreadPoolExecutor` for concurrent fetching.
- **MPI Distributed Crawler**: A distributed crawler using `mpi4py` in a master-worker model.
- **Analysis Script**: Compares sequential and multi-threaded crawlers within `analyze.py`, producing performance metrics and visualizations.
- **Configurable Parameters**: Seed URL, max pages, max depth, data to extract.
- **Fault-tolerant**: Handles dead URLs and network errors gracefully.
- **Load Balancing**: Dynamic URL distribution in parallel and distributed versions.

### Visualizations

- Execution time and pages per second comparison (`analyze.py`)
- Depth distribution comparison (`analyze.py` and individual crawlers)
- Word cloud of extracted content (`analyze.py` and individual crawlers)

Tracks key metrics: Execution time, pages crawled, pages per second, and speedup.

## Project Structure

web_crawler/
├── output/
│ ├── analyze/
│ │ ├── comparison/
│ │ │ ├── comparison_metrics.json
│ │ │ ├── depth_distribution_comparison.png
│ │ │ ├── execution_time_comparison.png
│ │ │ ├── pages_per_second_comparison.png
│ │ │ ├── word_cloud_comparison.png
│ │ ├── results_parallel.json
│ │ ├── results_sequential.json
│ ├── parallel - threads/
│ │ ├── depth_distribution.png
│ │ ├── results.json
│ │ ├── time_vs_pages.png
│ │ ├── word_cloud.png
│ ├── sequential/
│ │ ├── depth_distribution.png
│ │ ├── sequential_results.json
│ │ ├── time_vs_pages.png
│ │ ├── word_cloud.png
├── parallel - mpi/
│ ├── **pycache**/
│ ├── config.py
│ ├── main.py
├── parallel - threads/
│ ├── **pycache**/
│ ├── config.py
│ ├── main.py
├── sequential/
│ ├── **pycache**/
│ ├── config.py
│ ├── main.py
├── venv/
├── .gitignore
├── analyze.py
├── README.md
├── requirements.txt
├── test.py

````

## Prerequisites

- **Python 3.8+**: Ensure Python is installed on your system.
- **MPI Implementation**: Required for the MPI-based crawler (`parallel - mpi/main.py`).

  - **Windows**: Install MS-MPI or use WSL with MPICH/OpenMPI.
  - **Ubuntu**: `sudo apt-get install mpich` or `sudo apt-get install openmpi-bin`
  - **macOS**: `brew install mpich` or `brew install openmpi`

## Setup Instructions

1. **Clone the Repository**:

    ```bash
    git clone <repository_url>
    ```

2. **Create a Virtual Environment**:

    ```bash
    python -m venv venv
    ```

3. **Activate the Virtual Environment**:

    - Windows (PowerShell):

      ```bash
      .\venv\Scripts\activate
      ```

    - Unix/macOS:

      ```bash
      source venv/bin/activate
      ```

4. **Install Dependencies**:

    ```bash
    pip install -r requirements.txt
    ```

    Installed packages include:
    - `requests==2.31.0`
    - `beautifulsoup4==4.12.3`
    - `matplotlib==3.8.2`
    - `wordcloud==1.9.3`
    - `mpi4py==4.0.0`

## Usage

### Running Individual Crawlers

Ensure the virtual environment is activated.

- **Sequential Crawler**:

    ```bash
    python .\sequential\main.py
    ```

- **Multi-threaded Crawler**:

    ```bash
    python '.\parallel - threads\main.py'
    ```

- **MPI Distributed Crawler** (e.g., 1 master + 4 workers = 5 processes):

    ```bash
    mpirun -np 5 python '.\parallel - mpi\main.py'
    ```

### Comparing Crawlers with `analyze.py`

Run the analysis:

```bash
python .\analyze.py
````

It performs:

- Sequential crawl
- Parallel crawl
- Metric comparisons (pages crawled, execution time, pages per second, speedup)
- Visualizations generation

#### Outputs:

- **Console**: Performance summary
- **Files**:
  - `output/analyze/results_sequential.json`
  - `output/analyze/results_parallel.json`
  - `output/analyze/comparison/comparison_metrics.json`
- **Visualizations**:
  - `execution_time_comparison.png`
  - `pages_per_second_comparison.png`
  - `depth_distribution_comparison.png`
  - `word_cloud_comparison.png`

### Viewing Visualizations

Open `.png` files under:

- `output/sequential/`
- `output/parallel - threads/`
- `output/analyze/comparison/`

Analyze `comparison_metrics.json` for detailed metrics.

## Configuration

### Individual Crawlers

Edit `config.py` in:

- `sequential/`
- `parallel - threads/`
- `parallel - mpi/`

Key parameters:

- `SEED_URL`: Starting URL (default: `https://www.geeksforgeeks.org/`)
- `MAX_PAGES`: Maximum pages to crawl (default: `50`)
- `MAX_DEPTH`: Maximum depth (default: `2`)
- `NUM_THREADS`: Number of threads (for multi-threaded crawler) (default: `4`)
- `DATA_TO_EXTRACT`: Elements to extract (default: `['title', 'p', 'h1', 'meta_description']`)
- `OUTPUT_DIR`: Output directory (default: `"output"`)

### `analyze.py`

Settings are hardcoded in the `CrawlerConfig` class. Modify inside `analyze.py` if needed.

## Example Output

**Console Output from `analyze.py`:**

```text
2025-04-29 10:00:00,123 - INFO - Starting sequential crawl
2025-04-29 10:00:10,456 - INFO - Sequential crawl completed. Pages crawled: 50
2025-04-29 10:00:10,567 - INFO - Starting parallel crawl
2025-04-29 10:00:15,678 - INFO - Parallel crawl completed. Pages crawled: 50
2025-04-29 10:00:15,789 - INFO - Generated execution time comparison plot
2025-04-29 10:00:15,900 - INFO - GENERATED pages per second comparison plot
2025-04-29 10:00:16,011 - INFO - Generated depth distribution comparison plot
2025-04-29 10:00:16,122 - INFO - Generated word cloud comparison
2025-04-29 10:00:16,133 - INFO - Comparison metrics saved to output/analyze/comparison/comparison_metrics.json
```

**Comparison Summary:**

| Metric                        | Sequential | Parallel |
| ----------------------------- | ---------- | -------- |
| Pages Crawled                 | 50         | 50       |
| Execution Time (s)            | 10.11      | 5.11     |
| Pages per Second              | 4.95       | 9.78     |
| Speedup (Sequential/Parallel) | 1.98x      |          |

## Performance Analysis

- **Execution Time**: Parallel crawler is faster due to concurrent fetching.
- **Pages per Second**: Higher in the parallel crawler.
- **Speedup**: Computed as sequential time divided by parallel time.

### Bottlenecks

- **Network I/O**: HTTP requests dominate time; mitigated via parallelism.
- **Synchronization**: Minor overhead due to thread locks in the parallel crawler.
- **Load Balancing**: Dynamic URL distribution improves efficiency.
