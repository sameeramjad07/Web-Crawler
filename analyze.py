import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json
import os
import logging
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from wordcloud import WordCloud
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CrawlerConfig:
    """Minimal configuration for crawlers."""
    SEED_URL = "https://www.geeksforgeeks.org/"
    MAX_PAGES = 50
    MAX_DEPTH = 2
    DATA_TO_EXTRACT = ['title', 
                       #'p', 
                       'h1', 
                       'meta_description']
    OUTPUT_DIR = "outputs/analyze"
    NUM_THREADS = 4  # For parallel crawler

class SequentialCrawler:
    """Minimal sequential web crawler."""
    def __init__(self, config):
        self.seed_url = config.SEED_URL
        self.root_url = f"{urlparse(self.seed_url).scheme}://{urlparse(self.seed_url).netloc}"
        self.max_pages = config.MAX_PAGES
        self.max_depth = config.MAX_DEPTH
        self.data_to_extract = config.DATA_TO_EXTRACT
        self.output_dir = config.OUTPUT_DIR
        self.urls_to_crawl = [(self.seed_url, 0)]  # (url, depth)
        self.visited_urls = set()
        self.results = []
        self.pages_crawled = 0

    def fetch_page(self, url):
        try:
            response = requests.get(url, timeout=(3, 10))
            if response.status_code == 200:
                return response
            logger.warning(f"Failed to fetch {url}: Status code {response.status_code}")
            return None
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def extract_data(self, soup, url, depth):
        extracted_data = {'url': url, 'depth': depth}
        for item in self.data_to_extract:
            try:
                if item == 'title':
                    title_tag = soup.find('title')
                    extracted_data['title'] = title_tag.text.strip() if title_tag else 'No Title'
                elif item == 'meta_description':
                    meta_tag = soup.find('meta', attrs={'name': 'description'})
                    extracted_data['meta_description'] = meta_tag['content'].strip() if meta_tag and 'content' in meta_tag.attrs else 'No Meta Description'
                else:
                    elements = soup.find_all(item)
                    extracted_data[item] = [elem.text.strip() for elem in elements]
            except Exception as e:
                logger.error(f"Error extracting {item} from {url}: {e}")
                extracted_data[item] = []
        return extracted_data

    def parse_links(self, soup):
        links = []
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            full_url = urljoin(self.root_url, href)
            if full_url.startswith(self.root_url) and full_url not in self.visited_urls:
                links.append(full_url)
        return links

    def crawl(self):
        start_time = time.time()
        logger.info("Starting sequential crawl")

        while self.urls_to_crawl and self.pages_crawled < self.max_pages:
            url, depth = self.urls_to_crawl.pop(0)
            if url in self.visited_urls or depth > self.max_depth:
                continue
            self.visited_urls.add(url)
            self.pages_crawled += 1

            response = self.fetch_page(url)
            if not response:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            extracted_data = self.extract_data(soup, url, depth)
            self.results.append(extracted_data)
            links = self.parse_links(soup)
            self.urls_to_crawl.extend((link, depth + 1) for link in links)

        end_time = time.time()
        execution_time = end_time - start_time
        pages_per_second = self.pages_crawled / execution_time if execution_time > 0 else 0

        logger.info(f"Sequential crawl completed. Pages crawled: {self.pages_crawled}")
        self.save_results('results_sequential.json')
        return {
            'pages_crawled': self.pages_crawled,
            'execution_time': execution_time,
            'pages_per_second': pages_per_second,
            'results': self.results
        }

    def save_results(self, filename):
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, filename)
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=4)
        logger.info(f"Sequential results saved to {output_path}")

class ParallelCrawler:
    """Minimal parallel web crawler using threads."""
    def __init__(self, config):
        self.seed_url = config.SEED_URL
        self.root_url = f"{urlparse(self.seed_url).scheme}://{urlparse(self.seed_url).netloc}"
        self.max_pages = config.MAX_PAGES
        self.max_depth = config.MAX_DEPTH
        self.data_to_extract = config.DATA_TO_EXTRACT
        self.output_dir = config.OUTPUT_DIR
        self.num_threads = config.NUM_THREADS
        self.url_queue = Queue()
        self.url_queue.put((self.seed_url, 0))
        self.visited_urls = set()
        self.results = []
        self.pages_crawled = 0
        self.lock = threading.Lock()

    def fetch_page(self, url):
        try:
            response = requests.get(url, timeout=(3, 10))
            if response.status_code == 200:
                return response
            logger.warning(f"Failed to fetch {url}: Status code {response.status_code}")
            return None
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def extract_data(self, soup, url, depth):
        extracted_data = {'url': url, 'depth': depth}
        for item in self.data_to_extract:
            try:
                if item == 'title':
                    title_tag = soup.find('title')
                    extracted_data['title'] = title_tag.text.strip() if title_tag else 'No Title'
                elif item == 'meta_description':
                    meta_tag = soup.find('meta', attrs={'name': 'description'})
                    extracted_data['meta_description'] = meta_tag['content'].strip() if meta_tag and 'content' in meta_tag.attrs else 'No Meta Description'
                else:
                    elements = soup.find_all(item)
                    extracted_data[item] = [elem.text.strip() for elem in elements]
            except Exception as e:
                logger.error(f"Error extracting {item} from {url}: {e}")
                extracted_data[item] = []
        return extracted_data

    def parse_links(self, soup):
        links = []
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            full_url = urljoin(self.root_url, href)
            if full_url.startswith(self.root_url):
                links.append(full_url)
        return links

    def worker(self):
        while True:
            try:
                url, depth = self.url_queue.get(timeout=1)
                with self.lock:
                    if url in self.visited_urls or self.pages_crawled >= self.max_pages or depth > self.max_depth:
                        self.url_queue.task_done()
                        continue
                    self.visited_urls.add(url)
                    self.pages_crawled += 1

                response = self.fetch_page(url)
                if not response:
                    self.url_queue.task_done()
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                extracted_data = self.extract_data(soup, url, depth)
                with self.lock:
                    self.results.append(extracted_data)
                links = self.parse_links(soup)
                with self.lock:
                    for link in links:
                        if link not in self.visited_urls:
                            self.url_queue.put((link, depth + 1))
                self.url_queue.task_done()
            except self.url_queue.Empty:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")
                self.url_queue.task_done()

    def crawl(self):
        start_time = time.time()
        logger.info("Starting parallel crawl")

        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            for _ in range(self.num_threads):
                executor.submit(self.worker)

        end_time = time.time()
        execution_time = end_time - start_time
        pages_per_second = self.pages_crawled / execution_time if execution_time > 0 else 0

        logger.info(f"Parallel crawl completed. Pages crawled: {self.pages_crawled}")
        self.save_results('results_parallel.json')
        return {
            'pages_crawled': self.pages_crawled,
            'execution_time': execution_time,
            'pages_per_second': pages_per_second,
            'results': self.results
        }

    def save_results(self, filename):
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, filename)
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=4)
        logger.info(f"Parallel results saved to {output_path}")

class MPICrawlerData:
    """Load and process MPI crawler results."""
    def __init__(self, performance_metrics_path):
        self.performance_metrics_path = performance_metrics_path
        self.results = []  # Will be populated with dummy data since we don't have actual crawl results
        self.metrics = self._load_performance_metrics()
        
    def _load_performance_metrics(self):
        try:
            with open(self.performance_metrics_path, 'r') as f:
                metrics = json.load(f)
                logger.info(f"MPI performance metrics loaded successfully from {self.performance_metrics_path}")
                return metrics
        except Exception as e:
            logger.error(f"Failed to load MPI performance metrics: {e}")
            # Return default metrics if loading fails
            return {
                'pages_crawled': 0,
                'execution_time': 0,
                'pages_per_second': 0
            }
    
    def get_metrics(self):
        """Return metrics in the same format as other crawlers."""
        return {
            'pages_crawled': self.metrics.get('pages_crawled', 0),
            'execution_time': self.metrics.get('execution_time', 0),
            'pages_per_second': self.metrics.get('pages_per_second', 0),
            'results': self.results,  # Empty or dummy results
            'worker_metrics': self.metrics.get('worker_metrics', {}),
            'queue_size_history': self.metrics.get('queue_size_history', []),
            'worker_status_history': self.metrics.get('worker_status_history', []),
            'crawl_rate_history': self.metrics.get('crawl_rate_history', []),
            'timestamp_history': self.metrics.get('timestamp_history', [])
        }
    
    def generate_dummy_results(self, num_results=50, max_depth=2):
        """Generate dummy results for visualization purposes."""
        import random
        
        # Calculate a realistic depth distribution based on BFS behavior
        depth_distribution = []
        total = 0
        for depth in range(max_depth + 1):
            # More pages at middle depths, fewer at extremes
            count = min(num_results - total, int(num_results * (0.2 if depth == 0 else 0.5 if depth == 1 else 0.3)))
            depth_distribution.extend([depth] * count)
            total += count
        
        # Shuffle to simulate realistic crawling
        random.shuffle(depth_distribution)
        
        # Create dummy results
        self.results = [
            {
                'url': f"https://example.com/page{i}",
                'depth': depth,
                'title': f"Example Page {i}",
                'meta_description': f"This is example page {i} description",
                'h1': [f"Heading for page {i}"]
            }
            for i, depth in enumerate(depth_distribution[:num_results])
        ]
        
        return self.results

class CrawlerAnalyzer:
    """Compare sequential, parallel threads, and MPI parallel crawlers."""
    def __init__(self, config, mpi_performance_path="outputs/parallel - mpi/performance_metrics.json"):
        self.config = config
        self.output_dir = os.path.join(config.OUTPUT_DIR, 'comparison')
        self.mpi_performance_path = mpi_performance_path
        
        # Setup crawlers
        self.crawlers = [
            {'name': 'Sequential', 'instance': SequentialCrawler(config)},
            {'name': 'Parallel (Threads)', 'instance': ParallelCrawler(config)},
            {'name': 'Parallel (MPI)', 'instance': MPICrawlerData(mpi_performance_path)}
        ]

    def run(self):
        metrics_list = []
        results_list = []

        # Generate dummy results for MPI crawler since we only have performance metrics
        self.crawlers[2]['instance'].generate_dummy_results(
            num_results=self.crawlers[2]['instance'].metrics.get('pages_crawled', 50),
            max_depth=self.config.MAX_DEPTH
        )

        # Run sequential and thread-based crawlers
        for crawler in self.crawlers[:2]:
            logger.info(f"Running {crawler['name']} crawler")
            metrics = crawler['instance'].crawl()
            metrics_list.append(metrics)
            results_list.append(metrics['results'])
        
        # Add MPI metrics
        logger.info(f"Loading {self.crawlers[2]['name']} metrics")
        mpi_metrics = self.crawlers[2]['instance'].get_metrics()
        metrics_list.append(mpi_metrics)
        results_list.append(mpi_metrics['results'])

        # Generate visualizations and save metrics
        self.generate_visualizations(metrics_list, results_list)
        self.save_comparison_metrics(metrics_list)
        self.analyze_worker_distribution(metrics_list)

        # Print summary
        print("\nComparison Summary:")
        for crawler, metrics in zip(self.crawlers, metrics_list):
            print(f"{crawler['name']}:")
            print(f"  Pages Crawled: {metrics['pages_crawled']}")
            print(f"  Execution Time: {metrics['execution_time']:.2f} seconds")
            print(f"  Pages per Second: {metrics['pages_per_second']:.2f}")
        
        # Calculate speedups
        seq_time = metrics_list[0]['execution_time']
        thread_speedup = seq_time / metrics_list[1]['execution_time'] if metrics_list[1]['execution_time'] > 0 else 0
        mpi_speedup = seq_time / metrics_list[2]['execution_time'] if metrics_list[2]['execution_time'] > 0 else 0
        
        print(f"Speedup (Sequential / Parallel Threads): {thread_speedup:.2f}x")
        print(f"Speedup (Sequential / Parallel MPI): {mpi_speedup:.2f}x")
        print(f"MPI vs Threads Performance Ratio: {metrics_list[2]['pages_per_second'] / metrics_list[1]['pages_per_second']:.2f}x")

    def generate_visualizations(self, metrics_list, results_list):
        os.makedirs(self.output_dir, exist_ok=True)

        # Execution Time Comparison
        names = [crawler['name'] for crawler in self.crawlers]
        execution_times = [metrics['execution_time'] for metrics in metrics_list]
        plt.figure(figsize=(10, 6))
        bars = plt.bar(names, execution_times, color=['skyblue', 'lightgreen', 'coral'])
        plt.xlabel('Crawler Type')
        plt.ylabel('Execution Time (seconds)')
        plt.title('Execution Time Comparison')
        plt.grid(True, axis='y')
        
        # Add value labels on top of bars
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    f'{height:.2f}s',
                    ha='center', va='bottom')
            
        plt.savefig(os.path.join(self.output_dir, 'execution_time_comparison.png'))
        plt.close()
        logger.info("Generated execution time comparison plot")

        # Pages per Second Comparison
        pages_per_second = [metrics['pages_per_second'] for metrics in metrics_list]
        plt.figure(figsize=(10, 6))
        bars = plt.bar(names, pages_per_second, color=['skyblue', 'lightgreen', 'coral'])
        plt.xlabel('Crawler Type')
        plt.ylabel('Pages per Second')
        plt.title('Pages per Second Comparison')
        plt.grid(True, axis='y')
        
        # Add value labels on top of bars
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    f'{height:.2f}',
                    ha='center', va='bottom')
            
        plt.savefig(os.path.join(self.output_dir, 'pages_per_second_comparison.png'))
        plt.close()
        logger.info("Generated pages per second comparison plot")

        # Depth Distribution Comparison
        max_depth = self.config.MAX_DEPTH
        depth_counts = []
        for results in results_list:
            depths = [result['depth'] for result in results]
            counts = [depths.count(d) for d in range(max_depth + 1)]
            depth_counts.append(counts)

        fig, ax = plt.subplots(figsize=(12, 6))
        x = range(max_depth + 1)
        width = 0.25
        ax.bar([i - width for i in x], depth_counts[0], width, label=self.crawlers[0]['name'], color='skyblue')
        ax.bar([i for i in x], depth_counts[1], width, label=self.crawlers[1]['name'], color='lightgreen')
        ax.bar([i + width for i in x], depth_counts[2], width, label=self.crawlers[2]['name'], color='coral')
        ax.set_xlabel('Crawl Depth')
        ax.set_ylabel('Number of Pages')
        ax.set_title('Depth Distribution Comparison')
        ax.set_xticks(x)
        ax.legend()
        ax.grid(True, axis='y')
        plt.savefig(os.path.join(self.output_dir, 'depth_distribution_comparison.png'))
        plt.close()
        logger.info("Generated depth distribution comparison plot")

        # Speedup Comparison
        seq_time = metrics_list[0]['execution_time']
        speedups = [1.0]  # Sequential is baseline
        for metrics in metrics_list[1:]:
            exec_time = metrics['execution_time']
            speedup = seq_time / exec_time if exec_time > 0 else 0
            speedups.append(speedup)
        
        plt.figure(figsize=(10, 6))
        bars = plt.bar(names, speedups, color=['skyblue', 'lightgreen', 'coral'])
        plt.xlabel('Crawler Type')
        plt.ylabel('Speedup (relative to Sequential)')
        plt.title('Performance Speedup Comparison')
        plt.grid(True, axis='y')
        
        # Add value labels on top of bars
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    f'{height:.2f}x',
                    ha='center', va='bottom')
            
        plt.savefig(os.path.join(self.output_dir, 'speedup_comparison.png'))
        plt.close()
        logger.info("Generated speedup comparison plot")

        # Word Cloud (Combined)
        self.generate_word_cloud(results_list)

    def generate_word_cloud(self, results_list):
        all_text = []
        for results in results_list:
            for result in results:
                for key, value in result.items():
                    if key in self.config.DATA_TO_EXTRACT and isinstance(value, list):
                        all_text.extend(value)
                    elif key in self.config.DATA_TO_EXTRACT and isinstance(value, str):
                        all_text.append(value)
        text = ' '.join(all_text)
        if text.strip():
            wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text)
            plt.figure(figsize=(10, 5))
            plt.imshow(wordcloud, interpolation='bilinear')
            plt.axis('off')
            plt.title('Word Cloud of Extracted Content (Combined)')
            plt.savefig(os.path.join(self.output_dir, 'word_cloud_comparison.png'))
            plt.close()
            logger.info("Generated word cloud comparison")
        else:
            logger.warning("No text available for word cloud")

    def analyze_worker_distribution(self, metrics_list):
        """Analyze and visualize worker distribution for MPI crawler."""
        mpi_metrics = metrics_list[2]
        if 'worker_metrics' in mpi_metrics and mpi_metrics['worker_metrics']:
            worker_metrics = mpi_metrics['worker_metrics']
            
            # Worker pages processed distribution
            worker_ids = list(worker_metrics.keys())
            pages_processed = [worker_metrics[w]['pages_processed'] for w in worker_ids]
            
            plt.figure(figsize=(10, 6))
            bars = plt.bar(worker_ids, pages_processed, color='coral')
            plt.xlabel('Worker ID')
            plt.ylabel('Pages Processed')
            plt.title('MPI Worker Load Distribution')
            plt.grid(True, axis='y')
            
            # Add value labels
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                        f'{height}',
                        ha='center', va='bottom')
                
            plt.savefig(os.path.join(self.output_dir, 'mpi_worker_distribution.png'))
            plt.close()
            logger.info("Generated MPI worker distribution plot")
            
            # Average processing time per worker
            avg_times = [worker_metrics[w]['avg_processing_time'] for w in worker_ids]
            
            plt.figure(figsize=(10, 6))
            bars = plt.bar(worker_ids, avg_times, color='lightblue')
            plt.xlabel('Worker ID')
            plt.ylabel('Average Processing Time (s)')
            plt.title('MPI Worker Average Processing Time')
            plt.grid(True, axis='y')
            
            # Add value labels
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                        f'{height:.2f}s',
                        ha='center', va='bottom')
                
            plt.savefig(os.path.join(self.output_dir, 'mpi_worker_avg_time.png'))
            plt.close()
            logger.info("Generated MPI worker average time plot")
            
            # Crawl rate over time
            if 'crawl_rate_history' in mpi_metrics and 'timestamp_history' in mpi_metrics:
                crawl_rates = mpi_metrics['crawl_rate_history']
                timestamps = mpi_metrics['timestamp_history']
                
                if crawl_rates and timestamps and len(crawl_rates) == len(timestamps):
                    plt.figure(figsize=(10, 6))
                    plt.plot(timestamps, crawl_rates, 'o-', color='green')
                    plt.xlabel('Time (seconds)')
                    plt.ylabel('Crawl Rate (pages/second)')
                    plt.title('MPI Crawl Rate Over Time')
                    plt.grid(True)
                    plt.savefig(os.path.join(self.output_dir, 'mpi_crawl_rate_time.png'))
                    plt.close()
                    logger.info("Generated MPI crawl rate over time plot")

    def save_comparison_metrics(self, metrics_list):
        comparison_metrics = {
            crawler['name']: {
                'pages_crawled': metrics['pages_crawled'],
                'execution_time': metrics['execution_time'],
                'pages_per_second': metrics['pages_per_second']
            } for crawler, metrics in zip(self.crawlers, metrics_list)
        }
        
        # Calculate speedups
        seq_time = metrics_list[0]['execution_time']
        thread_speedup = seq_time / metrics_list[1]['execution_time'] if metrics_list[1]['execution_time'] > 0 else 0
        mpi_speedup = seq_time / metrics_list[2]['execution_time'] if metrics_list[2]['execution_time'] > 0 else 0
        
        comparison_metrics['speedups'] = {
            'thread_speedup': thread_speedup,
            'mpi_speedup': mpi_speedup,
            'mpi_vs_thread': metrics_list[2]['pages_per_second'] / metrics_list[1]['pages_per_second'] 
                if metrics_list[1]['pages_per_second'] > 0 else 0
        }
        
        # Add MPI specific metrics if available
        if 'worker_metrics' in metrics_list[2]:
            comparison_metrics['mpi_worker_metrics'] = metrics_list[2]['worker_metrics']

        output_path = os.path.join(self.output_dir, 'comparison_metrics.json')
        with open(output_path, 'w') as f:
            json.dump(comparison_metrics, f, indent=4)
        logger.info(f"Comparison metrics saved to {output_path}")

def main():
    config = CrawlerConfig()
    analyzer = CrawlerAnalyzer(config, "outputs/parallel - mpi/performance_metrics.json")
    analyzer.run()

if __name__ == '__main__':
    main()