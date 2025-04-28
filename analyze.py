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

class CrawlerAnalyzer:
    """Compare sequential and parallel crawlers."""
    def __init__(self, config):
        self.config = config
        self.output_dir = os.path.join(config.OUTPUT_DIR, 'comparison')
        self.crawlers = [
            {'name': 'Sequential', 'instance': SequentialCrawler(config)},
            {'name': 'Parallel', 'instance': ParallelCrawler(config)}
        ]

    def run(self):
        metrics_list = []
        results_list = []

        for crawler in self.crawlers:
            logger.info(f"Running {crawler['name']} crawler")
            metrics = crawler['instance'].crawl()
            metrics_list.append(metrics)
            results_list.append(metrics['results'])

        self.generate_visualizations(metrics_list, results_list)
        self.save_comparison_metrics(metrics_list)

        print("\nComparison Summary:")
        for crawler, metrics in zip(self.crawlers, metrics_list):
            print(f"{crawler['name']}:")
            print(f"  Pages Crawled: {metrics['pages_crawled']}")
            print(f"  Execution Time: {metrics['execution_time']:.2f} seconds")
            print(f"  Pages per Second: {metrics['pages_per_second']:.2f}")
        speedup = metrics_list[0]['execution_time'] / metrics_list[1]['execution_time'] if metrics_list[1]['execution_time'] > 0 else None
        print(f"Speedup (Sequential / Parallel): {speedup:.2f}x")

    def generate_visualizations(self, metrics_list, results_list):
        os.makedirs(self.output_dir, exist_ok=True)

        # Execution Time Comparison
        names = [crawler['name'] for crawler in self.crawlers]
        execution_times = [metrics['execution_time'] for metrics in metrics_list]
        plt.figure(figsize=(8, 6))
        plt.bar(names, execution_times, color=['skyblue', 'lightgreen'])
        plt.xlabel('Crawler Type')
        plt.ylabel('Execution Time (seconds)')
        plt.title('Execution Time Comparison')
        plt.grid(True, axis='y')
        plt.savefig(os.path.join(self.output_dir, 'execution_time_comparison.png'))
        plt.close()
        logger.info("Generated execution time comparison plot")

        # Pages per Second Comparison
        pages_per_second = [metrics['pages_per_second'] for metrics in metrics_list]
        plt.figure(figsize=(8, 6))
        plt.bar(names, pages_per_second, color=['skyblue', 'lightgreen'])
        plt.xlabel('Crawler Type')
        plt.ylabel('Pages per Second')
        plt.title('Pages per Second Comparison')
        plt.grid(True, axis='y')
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

        fig, ax = plt.subplots(figsize=(10, 6))
        x = range(max_depth + 1)
        width = 0.35
        ax.bar([i - width/2 for i in x], depth_counts[0], width, label='Sequential', color='skyblue')
        ax.bar([i + width/2 for i in x], depth_counts[1], width, label='Parallel', color='lightgreen')
        ax.set_xlabel('Crawl Depth')
        ax.set_ylabel('Number of Pages')
        ax.set_title('Depth Distribution Comparison')
        ax.set_xticks(x)
        ax.legend()
        ax.grid(True, axis='y')
        plt.savefig(os.path.join(self.output_dir, 'depth_distribution_comparison.png'))
        plt.close()
        logger.info("Generated depth distribution comparison plot")

        # Word Cloud (Combined)
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

    def save_comparison_metrics(self, metrics_list):
        comparison_metrics = {
            crawler['name']: {
                'pages_crawled': metrics['pages_crawled'],
                'execution_time': metrics['execution_time'],
                'pages_per_second': metrics['pages_per_second']
            } for crawler, metrics in zip(self.crawlers, metrics_list)
        }
        speedup = metrics_list[0]['execution_time'] / metrics_list[1]['execution_time'] if metrics_list[1]['execution_time'] > 0 else None
        comparison_metrics['speedup'] = speedup

        output_path = os.path.join(self.output_dir, 'comparison_metrics.json')
        with open(output_path, 'w') as f:
            json.dump(comparison_metrics, f, indent=4)
        logger.info(f"Comparison metrics saved to {output_path}")

def main():
    config = CrawlerConfig()
    analyzer = CrawlerAnalyzer(config)
    analyzer.run()

if __name__ == '__main__':
    main()