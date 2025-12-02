"""
Almabani BOQ Management System - Web GUI
Flask-based web interface for all pipeline functionalities.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from functools import wraps

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from openai import AsyncOpenAI

# Almabani imports
from almabani.config.settings import get_settings, get_openai_client, get_pinecone_client
from almabani.config.logging_config import setup_logging
from almabani.parsers.pipeline import ExcelToJsonPipeline
from almabani.vectorstore.indexer import JSONProcessor, VectorStoreIndexer
from almabani.core.embeddings import EmbeddingsService
from almabani.core.vector_store import VectorStoreService
from almabani.rate_matcher.matcher import RateMatcher
from almabani.rate_matcher.pipeline import RateFillerPipeline

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configure paths
BASE_DIR = Path(__file__).parent
UPLOAD_FOLDER = BASE_DIR / 'data' / 'uploads'
FILLS_FOLDER = BASE_DIR / 'data' / 'fills'
INDEXES_FOLDER = BASE_DIR / 'data' / 'indexes'

# Ensure directories exist
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
FILLS_FOLDER.mkdir(parents=True, exist_ok=True)
INDEXES_FOLDER.mkdir(parents=True, exist_ok=True)

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Allowed extensions
ALLOWED_EXCEL = {'xlsx', 'xls'}
ALLOWED_JSON = {'json'}


def allowed_file(filename: str, allowed: set) -> bool:
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def async_route(f):
    """Decorator to run async functions in Flask routes."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


def get_services():
    """Get configured services for pipeline operations."""
    settings = get_settings()
    openai_async = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout,
        max_retries=settings.openai_max_retries
    )
    pinecone_client = get_pinecone_client()
    
    embeddings_service = EmbeddingsService(
        async_client=openai_async,
        model=settings.openai_embedding_model,
        max_workers=settings.max_workers
    )
    
    vector_store_service = VectorStoreService(
        client=pinecone_client,
        index_name=settings.pinecone_index_name,
        environment=settings.pinecone_environment
    )
    
    return settings, openai_async, embeddings_service, vector_store_service


# ==================== Routes ====================

@app.route('/')
def home():
    """Home page with overview and quick actions."""
    settings = get_settings()
    return render_template('index.html', settings=settings)


@app.route('/parse', methods=['GET'])
def parse_page():
    """Parse page - Excel to JSON conversion."""
    return render_template('parse.html')


@app.route('/api/parse', methods=['POST'])
def api_parse():
    """API endpoint for parsing Excel to JSON (one JSON per sheet)."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename, ALLOWED_EXCEL):
            return jsonify({'error': 'Invalid file type. Only Excel files allowed.'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        input_path = UPLOAD_FOLDER / unique_filename
        file.save(str(input_path))
        
        # Get options
        sheets = request.form.get('sheets', '')
        sheet_list = [s.strip() for s in sheets.split(',') if s.strip()] if sheets else None
        
        # Create output directory
        output_dir = INDEXES_FOLDER / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Run parser (always multiple mode - one JSON per sheet)
        pipeline = ExcelToJsonPipeline()
        output_files = pipeline.process_file(
            input_file=input_path,
            output_mode="multiple",
            output_dir=output_dir,
            sheets=sheet_list
        )
        
        # Get relative paths for display
        output_names = [Path(f).name for f in output_files]
        
        return jsonify({
            'success': True,
            'message': f'Successfully parsed {len(output_files)} sheet(s)',
            'input_file': unique_filename,
            'output_files': output_names,
            'output_dir': str(output_dir.relative_to(BASE_DIR))
        })
        
    except Exception as e:
        logger.error(f"Parse error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/index', methods=['GET'])
def index_page():
    """Index page - JSON to Vector Store."""
    # List available JSON directories
    json_dirs = []
    if INDEXES_FOLDER.exists():
        for d in sorted(INDEXES_FOLDER.iterdir(), reverse=True):
            if d.is_dir():
                json_count = len(list(d.glob('*.json')))
                if json_count > 0:
                    json_dirs.append({
                        'name': d.name,
                        'path': str(d),
                        'json_count': json_count
                    })
    
    settings = get_settings()
    return render_template('index_vectors.html', json_dirs=json_dirs, settings=settings)


@app.route('/api/index', methods=['POST'])
@async_route
async def api_index():
    """API endpoint for indexing JSON to vector store."""
    try:
        data = request.get_json()
        input_path = data.get('input_path')
        namespace = data.get('namespace', '')
        create_new = data.get('create_index', False)
        
        if not input_path:
            return jsonify({'error': 'No input path provided'}), 400
        
        input_path = Path(input_path)
        if not input_path.exists():
            return jsonify({'error': f'Path does not exist: {input_path}'}), 400
        
        settings, openai_async, embeddings_service, vector_store_service = get_services()
        
        # Create or connect to index
        if create_new:
            await vector_store_service.create_index(
                dimension=settings.pinecone_dimension,
                metric=settings.pinecone_metric
            )
        else:
            vector_store_service.get_index()
        
        # Process JSON files
        processor = JSONProcessor()
        if input_path.is_file():
            documents = [processor.process_file(input_path)]
        else:
            documents = processor.process_directory(input_path)
        
        if not documents:
            return jsonify({'error': 'No documents found to index'}), 400
        
        # Index documents
        indexer = VectorStoreIndexer(embeddings_service, vector_store_service)
        result = await indexer.index_documents(
            documents,
            embedding_batch_size=settings.batch_size,
            upsert_batch_size=settings.pinecone_batch_size,
            namespace=namespace,
            max_workers=settings.max_workers
        )
        
        return jsonify({
            'success': True,
            'message': 'Indexing complete',
            'uploaded_count': result['uploaded_count'],
            'total_vectors': result['total_vectors_in_index'],
            'index_name': result['index_name'],
            'namespace': result['namespace']
        })
        
    except Exception as e:
        logger.error(f"Index error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/fill', methods=['GET'])
def fill_page():
    """Fill page - Rate filling interface."""
    settings = get_settings()
    return render_template('fill.html', settings=settings)


@app.route('/api/fill', methods=['POST'])
@async_route
async def api_fill():
    """API endpoint for filling rates in Excel."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename, ALLOWED_EXCEL):
            return jsonify({'error': 'Invalid file type. Only Excel files allowed.'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        input_path = UPLOAD_FOLDER / unique_filename
        file.save(str(input_path))
        
        # Get options
        sheet_name = request.form.get('sheet_name') or None
        namespace = request.form.get('namespace', '')
        threshold = request.form.get('threshold')
        threshold = float(threshold) if threshold else None
        top_k = request.form.get('top_k')
        top_k = int(top_k) if top_k else None
        
        settings, openai_async, embeddings_service, vector_store_service = get_services()
        
        # Apply defaults
        namespace = namespace if namespace else (settings.pinecone_namespace or "")
        threshold = threshold if threshold else settings.similarity_threshold
        top_k = top_k if top_k else settings.top_k
        
        # Create rate matcher
        rate_matcher = RateMatcher(
            async_openai_client=openai_async,
            embeddings_service=embeddings_service,
            vector_store_service=vector_store_service,
            similarity_threshold=threshold,
            top_k=top_k,
            model=settings.openai_chat_model,
            verbose_logging=False
        )
        
        # Create pipeline
        pipeline = RateFillerPipeline(rate_matcher)
        
        # Output file
        output_filename = f"{input_path.stem}_filled_{timestamp}.xlsx"
        output_path = FILLS_FOLDER / output_filename
        
        # Process file
        result = await pipeline.process_file(
            input_file=input_path,
            sheet_name=sheet_name,
            output_file=output_path,
            namespace=namespace,
            workers=settings.max_workers
        )
        
        report = result['report']
        
        return jsonify({
            'success': True,
            'message': 'Rate filling complete',
            'input_file': unique_filename,
            'output_file': output_filename,
            'summary_file': Path(result.get('summary_file', '')).name if result.get('summary_file') else None,
            'report': {
                'total_items': report['total_items'],
                'processed_items': report['processed_items'],
                'exact_matches': report['exact_matches'],
                'expert_matches': report['expert_matches'],
                'estimates': report['estimates'],
                'no_matches': report['no_matches'],
                'errors': report['errors']
            }
        })
        
    except Exception as e:
        logger.error(f"Fill error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/query', methods=['GET'])
def query_page():
    """Query page - Vector store search."""
    settings = get_settings()
    return render_template('query.html', settings=settings)


@app.route('/api/query', methods=['POST'])
@async_route
async def api_query():
    """API endpoint for querying vector store."""
    try:
        data = request.get_json()
        search_text = data.get('query', '')
        namespace = data.get('namespace', '')
        top_k = data.get('top_k', 5)
        threshold = data.get('threshold', 0.5)
        
        if not search_text:
            return jsonify({'error': 'No search query provided'}), 400
        
        settings, openai_async, embeddings_service, vector_store_service = get_services()
        
        # Generate embedding for query
        query_embedding = await embeddings_service.generate_embedding_async(search_text)
        
        # Search
        results = await vector_store_service.search(
            query_embedding=query_embedding,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True
        )
        
        # Filter by threshold and format results
        filtered_results = []
        for r in results:
            if r['score'] >= threshold:
                filtered_results.append({
                    'description': r['metadata'].get('description', r['text'][:100]),
                    'unit': r['metadata'].get('unit', ''),
                    'rate': r['metadata'].get('rate'),
                    'score': round(r['score'], 4),
                    'source': r['metadata'].get('sheet_name', ''),
                    'category': r['metadata'].get('category_path', '')
                })
        
        return jsonify({
            'success': True,
            'query': search_text,
            'results_count': len(filtered_results),
            'results': filtered_results
        })
        
    except Exception as e:
        logger.error(f"Query error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/settings', methods=['GET'])
def settings_page():
    """Settings page - View current configuration."""
    settings = get_settings()
    
    # Get index stats if possible
    index_stats = None
    try:
        pinecone_client = get_pinecone_client()
        vector_store = VectorStoreService(
            client=pinecone_client,
            index_name=settings.pinecone_index_name,
            environment=settings.pinecone_environment
        )
        index_stats = vector_store.get_stats()
    except Exception as e:
        logger.warning(f"Could not get index stats: {e}")
    
    return render_template('settings.html', settings=settings, index_stats=index_stats)


@app.route('/download/<folder>/<filename>')
def download_file(folder: str, filename: str):
    """Download a file from the specified folder."""
    try:
        if folder == 'fills':
            file_path = FILLS_FOLDER / filename
        elif folder == 'indexes':
            file_path = INDEXES_FOLDER / filename
        elif folder == 'uploads':
            file_path = UPLOAD_FOLDER / filename
        else:
            return jsonify({'error': 'Invalid folder'}), 400
        
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(str(file_path), as_attachment=True)
        
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/download/indexes/<subfolder>/<filename>')
def download_index_file(subfolder: str, filename: str):
    """Download a file from indexes subfolder."""
    try:
        file_path = INDEXES_FOLDER / subfolder / filename
        
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(str(file_path), as_attachment=True)
        
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/files/<folder>')
def list_files(folder: str):
    """List files in a folder."""
    try:
        if folder == 'fills':
            folder_path = FILLS_FOLDER
        elif folder == 'indexes':
            folder_path = INDEXES_FOLDER
        elif folder == 'uploads':
            folder_path = UPLOAD_FOLDER
        else:
            return jsonify({'error': 'Invalid folder'}), 400
        
        files = []
        for f in sorted(folder_path.iterdir(), reverse=True):
            if f.is_file():
                files.append({
                    'name': f.name,
                    'size': f.stat().st_size,
                    'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                })
        
        return jsonify({'files': files})
        
    except Exception as e:
        logger.error(f"List files error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/json-files')
def list_json_files():
    """List all JSON files available for indexing."""
    try:
        files = []
        
        # Check indexes folder for JSON directories
        if INDEXES_FOLDER.exists():
            for d in sorted(INDEXES_FOLDER.iterdir(), reverse=True):
                if d.is_dir():
                    for f in d.glob('*.json'):
                        files.append({
                            'name': f.name,
                            'path': str(f),
                            'size': f.stat().st_size,
                            'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                            'folder': d.name
                        })
        
        # Also check data/output/json folder
        data_json_folder = Path(__file__).parent.parent / 'data' / 'output' / 'json'
        if data_json_folder.exists():
            for f in data_json_folder.glob('*.json'):
                files.append({
                    'name': f.name,
                    'path': str(f),
                    'size': f.stat().st_size,
                    'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    'folder': 'data/output/json'
                })
        
        return jsonify({'files': files})
        
    except Exception as e:
        logger.error(f"List JSON files error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/index-stats')
def api_index_stats():
    """Get vector store index statistics."""
    try:
        settings = get_settings()
        pinecone_client = get_pinecone_client()
        
        vector_store = VectorStoreService(
            client=pinecone_client,
            index_name=settings.pinecone_index_name,
            environment=settings.pinecone_environment
        )
        
        stats = vector_store.get_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/files')
def files_page():
    """Files management page."""
    return render_template('files.html')


@app.route('/api/delete-file', methods=['POST'])
def api_delete_file():
    """Delete a file from uploads, fills, or indexes."""
    try:
        data = request.get_json()
        folder = data.get('folder')
        filename = data.get('filename')
        
        if not folder or not filename:
            return jsonify({'error': 'Folder and filename are required'}), 400
        
        # Determine folder path
        if folder == 'uploads':
            folder_path = UPLOAD_FOLDER
        elif folder == 'fills':
            folder_path = FILLS_FOLDER
        elif folder == 'indexes':
            folder_path = INDEXES_FOLDER
        else:
            return jsonify({'error': 'Invalid folder'}), 400
        
        # Construct file path and validate it's within the folder
        file_path = folder_path / filename
        
        # Security: ensure file is within allowed folder
        try:
            file_path.resolve().relative_to(folder_path.resolve())
        except ValueError:
            return jsonify({'error': 'Invalid file path'}), 400
        
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        # Delete file or directory
        if file_path.is_dir():
            import shutil
            shutil.rmtree(file_path)
            logger.info(f"Deleted directory: {file_path}")
        else:
            file_path.unlink()
            logger.info(f"Deleted file: {file_path}")
        
        return jsonify({'success': True, 'message': f'Deleted {filename}'})
        
    except Exception as e:
        logger.error(f"Delete file error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete-json-file', methods=['POST'])
def api_delete_json_file():
    """Delete a specific JSON file from an indexes subfolder."""
    try:
        data = request.get_json()
        subfolder = data.get('subfolder')
        filename = data.get('filename')
        
        if not subfolder or not filename:
            return jsonify({'error': 'Subfolder and filename are required'}), 400
        
        # Construct file path
        file_path = INDEXES_FOLDER / subfolder / filename
        
        # Security: ensure file is within indexes folder
        try:
            file_path.resolve().relative_to(INDEXES_FOLDER.resolve())
        except ValueError:
            return jsonify({'error': 'Invalid file path'}), 400
        
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        # Delete file
        file_path.unlink()
        logger.info(f"Deleted JSON file: {file_path}")
        
        # Check if folder is empty and delete it too
        parent_folder = file_path.parent
        if parent_folder.exists() and not any(parent_folder.iterdir()):
            parent_folder.rmdir()
            logger.info(f"Deleted empty folder: {parent_folder}")
        
        return jsonify({'success': True, 'message': f'Deleted {filename}'})
        
    except Exception as e:
        logger.error(f"Delete JSON file error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete-all', methods=['POST'])
def api_delete_all():
    """Delete all files in a folder."""
    try:
        data = request.get_json()
        folder = data.get('folder')
        
        if not folder:
            return jsonify({'error': 'Folder is required'}), 400
        
        # Determine folder path
        if folder == 'uploads':
            folder_path = UPLOAD_FOLDER
        elif folder == 'fills':
            folder_path = FILLS_FOLDER
        elif folder == 'indexes':
            folder_path = INDEXES_FOLDER
        else:
            return jsonify({'error': 'Invalid folder'}), 400
        
        # Delete all contents
        import shutil
        deleted_count = 0
        for item in folder_path.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            deleted_count += 1
        
        logger.info(f"Deleted {deleted_count} items from {folder}")
        return jsonify({'success': True, 'message': f'Deleted {deleted_count} items from {folder}'})
        
    except Exception as e:
        logger.error(f"Delete all error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    return render_template('error.html', error='Page not found', code=404), 404


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    return render_template('error.html', error='Internal server error', code=500), 500


# ==================== Main ====================

def run_app(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
    """Run the Flask application."""
    logger.info(f"Starting Almabani GUI on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    run_app(debug=True)
