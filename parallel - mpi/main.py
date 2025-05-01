import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json
import os
import pickle
import logging
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from wordcloud import WordCloud
from mpi4py import MPI
from config import Config
import argparse
import numpy as np
from collections import defaultdict

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MPIDistributedCrawler:
    def __init__(self, config, comm, rank, size):
        """Initialize the MPI distributed crawler."""
        self.config = config
        self.comm = comm
        self.rank = rank
        self.size = size
        self.root_url = f"{urlparse(config.SEED_URL).scheme}://{urlparse(config.SEED_URL).netloc}"
        self.output_dir = config.OUTPUT_DIR
        
        # Performance metrics
        self.start_time = None
        self.worker_stats = {
            'urls_processed': 0,
            'success_count': 0,
            'error_count': 0,
            'idle_time': 0,
            'processing_time': 0,
            'last_task_time': 0
        }

    def fetch_page(self, url):
        """Fetch a web page and return its response or None if it fails."""
        try:
            response = requests.get(url, timeout=(3, 30))
            if response.status_code == 200:
                return response
            else:
                logger.warning(f"Worker {self.rank} failed to fetch {url}: Status code {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.error(f"Worker {self.rank} error fetching {url}: {e}")
            return None

    def extract_data(self, soup, url, depth):
        """Extract specified data from the page."""
        extracted_data = {'url': url, 'depth': depth}
        for item in self.config.DATA_TO_EXTRACT:
            try:
                if item == 'title':
                    title_tag = soup.find('title')
                    extracted_data['title'] = title_tag.text.strip() if title_tag else 'No Title'
                elif item == 'meta_description':
                    meta_tag = soup.find('meta', attrs={'name': 'description'})
                    extracted_data['meta_description'] = meta_tag['content'].strip() if meta_tag and 'content' in meta_tag.attrs else 'No Meta Description'
                elif item.startswith('.'):
                    elements = soup.select(item)
                    extracted_data[item] = [elem.text.strip() for elem in elements]
                else:
                    elements = soup.find_all(item)
                    extracted_data[item] = [elem.text.strip() for elem in elements]
            except Exception as e:
                logger.error(f"Worker {self.rank} error extracting {item} from {url}: {e}")
                extracted_data[item] = []
        return extracted_data

    def parse_links(self, soup):
        """Parse HTML to extract links."""
        links = []
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            full_url = urljoin(self.root_url, href)
            if full_url.startswith(self.root_url):
                links.append(full_url)
        return links

    def master(self):
        """Master process: Assign URLs and collect results with dynamic load balancing."""
        self.start_time = time.time()
        urls_to_crawl = [(self.config.SEED_URL, 0)]  # (url, depth)
        visited_urls = set()
        results = []
        pages_crawled = 0
        idle_workers = list(range(1, self.size))
        active_tasks = {}  # worker_rank -> (url, depth, start_time)
        
        # Worker performance metrics
        worker_metrics = {worker: {
            'pages_processed': 0,
            'success_count': 0,
            'error_count': 0,
            'total_processing_time': 0,
            'avg_processing_time': 0,
            'idle_time': 0
        } for worker in range(1, self.size)}
        
        # Time metrics
        last_status_time = time.time()
        status_interval = 5  # Report status every 5 seconds
        
        # Queue metrics
        queue_size_history = []
        worker_status_history = []  # Track idle vs. busy workers
        crawl_rate_history = []
        timestamp_history = []

        # Main loop
        while pages_crawled < self.config.MAX_PAGES and (urls_to_crawl or active_tasks):
            current_time = time.time()
            
            # Record metrics periodically
            if current_time - last_status_time >= status_interval:
                elapsed = current_time - self.start_time
                pages_per_second = pages_crawled / elapsed if elapsed > 0 else 0
                queue_size_history.append(len(urls_to_crawl))
                worker_status_history.append((len(idle_workers), self.size - len(idle_workers) - 1))  # (idle, busy)
                crawl_rate_history.append(pages_per_second)
                timestamp_history.append(elapsed)
                
                logger.info(f"Status: {pages_crawled}/{self.config.MAX_PAGES} pages, "
                           f"Queue: {len(urls_to_crawl)}, "
                           f"Workers: {self.size - len(idle_workers) - 1} busy / {len(idle_workers)} idle, "
                           f"Rate: {pages_per_second:.2f} pages/sec")
                last_status_time = current_time

            # Check for workers that might be stuck (timeout mechanism)
            for worker, (url, depth, task_start_time) in list(active_tasks.items()):
                if current_time - task_start_time > self.config.WORKER_TIMEOUT:
                    logger.warning(f"Worker {worker} timed out on {url}. Reassigning task.")
                    # Consider this worker failed and reassign its task
                    urls_to_crawl.append((url, depth))  # Put the URL back in the queue
                    worker_metrics[worker]['error_count'] += 1
                    
                    # Force termination and restart of the worker (in a real system)
                    # Here we just simulate by sending a message and expecting worker to reset
                    self.comm.send(('RESET', None), dest=worker, tag=1)
                    del active_tasks[worker]
                    idle_workers.append(worker)

            # Dynamic load balancing: assign tasks to idle workers
            while idle_workers and urls_to_crawl and pages_crawled < self.config.MAX_PAGES:
                url, depth = urls_to_crawl.pop(0)
                if url in visited_urls or depth > self.config.MAX_DEPTH:
                    continue
                    
                visited_urls.add(url)
                # Prioritize workers with better performance
                if len(idle_workers) > 1 and pages_crawled > self.size:
                    # Sort workers by their average processing time (ascending)
                    sorted_workers = sorted(idle_workers, 
                                         key=lambda w: worker_metrics[w]['avg_processing_time'] 
                                         if worker_metrics[w]['pages_processed'] > 0 else float('inf'))
                    worker = sorted_workers[0]
                    idle_workers.remove(worker)
                else:
                    worker = idle_workers.pop(0)
                
                self.comm.send(('CRAWL', (url, depth)), dest=worker, tag=1)
                active_tasks[worker] = (url, depth, time.time())
                pages_crawled += 1
                logger.info(f"Master assigned {url} to worker {worker} (Depth: {depth})")

            # Collect results from workers
            for worker in list(active_tasks.keys()):
                if self.comm.Iprobe(source=worker, tag=2):
                    data = self.comm.recv(source=worker, tag=2)
                    task_result, task_metrics = pickle.loads(data)
                    
                    # Update worker metrics
                    url, depth, _ = active_tasks[worker]
                    task_duration = time.time() - active_tasks[worker][2]
                    worker_metrics[worker]['pages_processed'] += 1
                    worker_metrics[worker]['total_processing_time'] += task_duration
                    worker_metrics[worker]['avg_processing_time'] = (
                        worker_metrics[worker]['total_processing_time'] / 
                        worker_metrics[worker]['pages_processed']
                    )
                    
                    if task_result['success']:
                        worker_metrics[worker]['success_count'] += 1
                        # Process extracted data and links
                        extracted_data, links = task_result['data'], task_result['links']
                        if extracted_data:
                            results.append(extracted_data)
                        # Add new links to crawl queue
                        if links:
                            new_depth = depth + 1
                            for link in links:
                                if link not in visited_urls and new_depth <= self.config.MAX_DEPTH:
                                    urls_to_crawl.append((link, new_depth))
                    else:
                        worker_metrics[worker]['error_count'] += 1
                        logger.warning(f"Worker {worker} failed to process {url}: {task_result.get('error', 'Unknown error')}")
                    
                    idle_workers.append(worker)
                    del active_tasks[worker]
                    logger.debug(f"Master received results from worker {worker}")

        # Terminate idle workers
        for worker in idle_workers:
            self.comm.send(('TERMINATE', None), dest=worker, tag=1)

        # Collect remaining results and terminate active workers
        for worker in list(active_tasks.keys()):
            # Wait for any remaining results (with timeout)
            if self.comm.Iprobe(source=worker, tag=2):
                data = self.comm.recv(source=worker, tag=2)
                task_result, task_metrics = pickle.loads(data)
                if task_result['success']:
                    extracted_data, links = task_result['data'], task_result['links']
                    if extracted_data:
                        results.append(extracted_data)
            
            # Terminate this worker
            self.comm.send(('TERMINATE', None), dest=worker, tag=1)
            logger.info(f"Terminated worker {worker}")

        end_time = time.time()
        execution_time = end_time - self.start_time
        pages_per_second = pages_crawled / execution_time if execution_time > 0 else 0

        logger.info(f"Crawl completed. Pages crawled: {pages_crawled}")
        logger.info(f"Execution time: {execution_time:.2f} seconds")
        logger.info(f"Pages per second: {pages_per_second:.2f}")

        # Save and visualize results
        self.save_results(results)
        self.generate_visualizations(results)
        
        # Generate performance analysis
        metrics = {
            'pages_crawled': pages_crawled,
            'execution_time': execution_time,
            'pages_per_second': pages_per_second,
            'worker_metrics': worker_metrics,
            'queue_size_history': queue_size_history,
            'worker_status_history': worker_status_history,
            'crawl_rate_history': crawl_rate_history,
            'timestamp_history': timestamp_history
        }
        
        self.generate_performance_analysis(metrics)
        
        return metrics

    def worker(self):
        """Worker process: Fetch URLs and return results with error handling."""
        while True:
            # Track idle time
            idle_start = time.time()
            
            # Receive task from master
            command, task_data = self.comm.recv(source=0, tag=1)
            
            # Update idle time
            self.worker_stats['idle_time'] += (time.time() - idle_start)
            
            # Process the command
            if command == 'TERMINATE':
                break
            elif command == 'RESET':
                # Reset worker state and continue
                self.worker_stats = {
                    'urls_processed': 0,
                    'success_count': 0,
                    'error_count': 0,
                    'idle_time': 0,
                    'processing_time': 0,
                    'last_task_time': 0
                }
                continue
            
            # Normal crawl task
            url, depth = task_data
            task_start = time.time()
            logger.info(f"Worker {self.rank} processing {url} (Depth: {depth})")
            
            # Initialize result structure
            task_result = {
                'success': False,
                'data': None,
                'links': [],
                'error': None
            }
            
            try:
                # Fetch and process page
                response = self.fetch_page(url)
                if not response:
                    task_result['error'] = "Failed to fetch page"
                    self.worker_stats['error_count'] += 1
                else:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    extracted_data = self.extract_data(soup, url, depth)
                    links = self.parse_links(soup)
                    
                    task_result['success'] = True
                    task_result['data'] = extracted_data
                    task_result['links'] = links
                    self.worker_stats['success_count'] += 1
            except Exception as e:
                logger.error(f"Worker {self.rank} encountered an error: {e}")
                task_result['error'] = str(e)
                self.worker_stats['error_count'] += 1
            
            # Update worker stats
            task_end = time.time()
            task_duration = task_end - task_start
            self.worker_stats['urls_processed'] += 1
            self.worker_stats['processing_time'] += task_duration
            self.worker_stats['last_task_time'] = task_duration
            
            # Send results and worker stats to master
            self.comm.send(pickle.dumps((task_result, self.worker_stats)), dest=0, tag=2)

    def save_results(self, results):
        """Save crawled data to a JSON file."""
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, 'results.json')
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=4)
        logger.info(f"Results saved to {output_path}")

    def generate_visualizations(self, results):
        """Generate visualizations for crawled data."""
        os.makedirs(self.output_dir, exist_ok=True)

        # Bar Chart: Pages per Depth
        depths = [result['depth'] for result in results]
        depth_counts = {}
        for depth in range(self.config.MAX_DEPTH + 1):
            depth_counts[depth] = depths.count(depth)
        
        plt.figure(figsize=(8, 6))
        plt.bar(depth_counts.keys(), depth_counts.values(), color='skyblue')
        plt.xlabel('Crawl Depth')
        plt.ylabel('Number of Pages')
        plt.title('Pages Crawled per Depth')
        plt.grid(True, axis='y')
        plt.savefig(os.path.join(self.output_dir, 'depth_distribution.png'))
        plt.close()
        logger.info("Generated depth distribution bar chart")

        # Word Cloud: Extracted Text
        all_text = []
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
            plt.title('Word Cloud of Extracted Content')
            plt.savefig(os.path.join(self.output_dir, 'word_cloud.png'))
            plt.close()
            logger.info("Generated word cloud")
        else:
            logger.warning("No text available for word cloud")

    def generate_performance_analysis(self, metrics):
        """Generate performance analysis visualizations."""
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 1. Worker Utilization Chart
        worker_metrics = metrics['worker_metrics']
        worker_ids = list(worker_metrics.keys())
        success_counts = [worker_metrics[w]['success_count'] for w in worker_ids]
        error_counts = [worker_metrics[w]['error_count'] for w in worker_ids]
        avg_times = [worker_metrics[w]['avg_processing_time'] for w in worker_ids]
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12))
        
        # Pages processed per worker (stacked bar)
        width = 0.35
        ax1.bar(worker_ids, success_counts, width, label='Successful', color='green')
        ax1.bar(worker_ids, error_counts, width, bottom=success_counts, label='Failed', color='red')
        ax1.set_xlabel('Worker ID')
        ax1.set_ylabel('Pages Processed')
        ax1.set_title('Worker Utilization')
        ax1.legend()
        ax1.grid(True, axis='y')
        
        # Average processing time per worker
        ax2.bar(worker_ids, avg_times, color='blue')
        ax2.set_xlabel('Worker ID')
        ax2.set_ylabel('Average Processing Time (s)')
        ax2.set_title('Worker Processing Times')
        ax2.grid(True, axis='y')
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, 'worker_performance.png'))
        plt.close()
        
        # 2. Crawler Performance Over Time
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # Queue size over time
        ax1.plot(metrics['timestamp_history'], metrics['queue_size_history'], 'b-', label='Queue Size')
        ax1.set_xlabel('Elapsed Time (s)')
        ax1.set_ylabel('URL Queue Size')
        ax1.set_title('URL Queue Size Over Time')
        ax1.grid(True)
        
        # Crawl rate over time
        ax2.plot(metrics['timestamp_history'], metrics['crawl_rate_history'], 'g-', label='Pages/Second')
        ax2.set_xlabel('Elapsed Time (s)')
        ax2.set_ylabel('Pages per Second')
        ax2.set_title('Crawl Rate Over Time')
        ax2.grid(True)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, 'crawler_performance.png'))
        plt.close()
        
        # 3. Worker Status Over Time
        idle_counts = [status[0] for status in metrics['worker_status_history']]
        busy_counts = [status[1] for status in metrics['worker_status_history']]
        
        plt.figure(figsize=(10, 6))
        plt.stackplot(metrics['timestamp_history'], 
                     [idle_counts, busy_counts],
                     labels=['Idle Workers', 'Busy Workers'],
                     colors=['orange', 'blue'])
        plt.xlabel('Elapsed Time (s)')
        plt.ylabel('Number of Workers')
        plt.title('Worker Status Over Time')
        plt.legend(loc='upper right')
        plt.grid(True)
        plt.savefig(os.path.join(self.output_dir, 'worker_status.png'))
        plt.close()
        
        # 4. Save metrics to JSON
        with open(os.path.join(self.output_dir, 'performance_metrics.json'), 'w') as f:
            # Convert non-serializable data to lists for JSON
            json_metrics = {
                'pages_crawled': metrics['pages_crawled'],
                'execution_time': metrics['execution_time'],
                'pages_per_second': metrics['pages_per_second'],
                'worker_metrics': metrics['worker_metrics'],
                'queue_size_history': metrics['queue_size_history'],
                'worker_status_history': [list(status) for status in metrics['worker_status_history']],
                'crawl_rate_history': metrics['crawl_rate_history'],
                'timestamp_history': metrics['timestamp_history']
            }
            json.dump(json_metrics, f, indent=4)

    def run_scalability_test(self, worker_counts):
        """
        Run scalability tests with different worker counts.
        This would typically be run as a separate script, but included here for completeness.
        """
        if self.rank == 0:
            results = {}
            for count in worker_counts:
                # In a real implementation, you would need to spawn processes dynamically
                # For demonstration, we'll just simulate the results based on a model
                simulated_time = self.config.MAX_PAGES / (2 * count) + 5  # Simple model for demo
                simulated_speedup = worker_counts[0] / count
                results[count] = {
                    'execution_time': simulated_time,
                    'speedup': worker_counts[0] / simulated_time,
                    'efficiency': (worker_counts[0] / simulated_time) / count
                }
            
            # Plot speedup and efficiency
            counts = list(results.keys())
            speedups = [results[c]['speedup'] for c in counts]
            efficiencies = [results[c]['efficiency'] for c in counts]
            
            plt.figure(figsize=(10, 6))
            plt.plot(counts, speedups, 'bo-', label='Speedup')
            plt.plot(counts, [c for c in counts], 'r--', label='Linear Speedup')
            plt.xlabel('Number of Workers')
            plt.ylabel('Speedup')
            plt.title('Speedup vs. Number of Workers')
            plt.legend()
            plt.grid(True)
            plt.savefig(os.path.join(self.output_dir, 'speedup.png'))
            plt.close()
            
            plt.figure(figsize=(10, 6))
            plt.plot(counts, efficiencies, 'go-')
            plt.xlabel('Number of Workers')
            plt.ylabel('Efficiency')
            plt.title('Efficiency vs. Number of Workers')
            plt.grid(True)
            plt.savefig(os.path.join(self.output_dir, 'efficiency.png'))
            plt.close()
            
            return results
        return None

    def run(self):
        """Run the MPI distributed crawler."""
        if self.rank == 0:
            metrics = self.master()
            print(f"\nPerformance Summary:")
            print(f"Pages Crawled: {metrics['pages_crawled']}")
            print(f"Execution Time: {metrics['execution_time']:.2f} seconds")
            print(f"Pages per Second: {metrics['pages_per_second']:.2f}")
            
            # Print per-worker statistics
            print("\nWorker Statistics:")
            for worker_id, stats in metrics['worker_metrics'].items():
                print(f"Worker {worker_id}:")
                print(f"  Pages Processed: {stats['pages_processed']}")
                print(f"  Success Rate: {stats['success_count'] / max(1, stats['pages_processed']):.2%}")
                print(f"  Avg Processing Time: {stats['avg_processing_time']:.2f} seconds")
            
            # Identify bottlenecks
            print("\nBottleneck Analysis:")
            if metrics['pages_per_second'] < 0.5:
                print("- Low crawl rate detected. Possible network I/O bottleneck.")
            
            idle_percentage = sum(status[0] for status in metrics['worker_status_history']) / (
                sum(status[0] + status[1] for status in metrics['worker_status_history']))
            if idle_percentage > 0.3:
                print(f"- High worker idle time ({idle_percentage:.1%}). Possible load balancing issue.")
            
            avg_times = [stats['avg_processing_time'] for stats in metrics['worker_metrics'].values()]
            if max(avg_times) / (min(avg_times) + 0.001) > 2:
                print("- High variance in worker processing times. Check for heterogeneous workers or uneven workload.")
            
            return metrics
        else:
            self.worker()
            return None

# Add a Config class with default values if missing from config module
class DefaultConfig:
    SEED_URL = "https://example.com"
    MAX_PAGES = 100
    MAX_DEPTH = 3
    OUTPUT_DIR = "crawler_output"
    DATA_TO_EXTRACT = ['title', 'meta_description', 'p', 'h1', 'h2', 'h3']
    WORKER_TIMEOUT = 60  # Seconds before considering a worker hung

def main():
    parser = argparse.ArgumentParser(description="MPI distributed web crawler")
    parser.add_argument('--config', default='config.Config', help='Config class to use (default: config.Config)')
    parser.add_argument('--seed', help='Seed URL to start crawling')
    parser.add_argument('--output', help='Output directory for results')
    parser.add_argument('--max-pages', type=int, help='Maximum pages to crawl')
    parser.add_argument('--max-depth', type=int, help='Maximum depth to crawl')
    parser.add_argument('--scalability-test', action='store_true', help='Run scalability test')
    args = parser.parse_args()

    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    if size < 2:
        if rank == 0:
            logger.error("At least 2 processes are required (1 master + 1 worker)")
        return

    # Try to load the specified config, fall back to default if not found
    try:
        module_name, class_name = args.config.rsplit('.', 1)
        config_module = __import__(module_name, fromlist=[class_name])
        config_class = getattr(config_module, class_name)
        config = config_class()
    except (ImportError, AttributeError):
        logger.warning(f"Config {args.config} not found. Using default config.")
        config = DefaultConfig()
    
    # Override config with command line arguments
    if args.seed:
        config.SEED_URL = args.seed
    if args.output:
        config.OUTPUT_DIR = args.output
    if args.max_pages:
        config.MAX_PAGES = args.max_pages
    if args.max_depth:
        config.MAX_DEPTH = args.max_depth

    crawler = MPIDistributedCrawler(config, comm, rank, size)
    
    if args.scalability_test:
        if rank == 0:
            # Run scalability test (simulated)
            worker_counts = [1, 2, 4, 8, 16]
            results = crawler.run_scalability_test(worker_counts)
            print("\nScalability Test Results:")
            for count, metrics in results.items():
                print(f"Workers: {count}, Time: {metrics['execution_time']:.2f}s, "
                      f"Speedup: {metrics['speedup']:.2f}x, Efficiency: {metrics['efficiency']:.2%}")
            # Send TERMINATE to all workers
            for worker in range(1, size):
                comm.send(('TERMINATE', None), dest=worker, tag=1)
        else:
            # Workers wait for TERMINATE command
            crawler.worker()
    else:
        # Run normal crawler
        crawler.run()

if __name__ == '__main__':
    main()