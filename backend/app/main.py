"""
Almabani BOQ Management System - Web GUI
Flask-based web interface for all pipeline functionalities.
"""
import asyncio
import logging
import os
import shutil
import uuid
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from functools import wraps

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from openai import AsyncOpenAI

# Almabani imports
from almabani.config.settings import get_settings, get_openai_client, get_vector_store
from almabani.config.logging_config import setup_logging
from almabani.parsers.pipeline import ExcelToJsonPipeline
from almabani.vectorstore.indexer import JSONProcessor, VectorStoreIndexer
from almabani.core.embeddings import EmbeddingsService
from almabani.core.vector_store import VectorStoreService
from almabani.rate_matcher.matcher import RateMatcher
from almabani.rate_matcher.pipeline import RateFillerPipeline
from almabani.core.storage import get_storage

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

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
    
    embeddings_service = EmbeddingsService(
        async_client=openai_async,
        model=settings.openai_embedding_model,
        max_workers=settings.max_workers
    )
    
    vector_store_service = get_vector_store()
    
    return settings, openai_async, embeddings_service, vector_store_service

# ==================== Helper Functions for Temp Files ====================

def create_temp_dir() -> Path:
    """Create a temporary directory for processing."""
    tmp_path = Path(tempfile.mkdtemp(prefix='almabani_'))
    return tmp_path

def cleanup_temp_dir(path: Path):
    """Remove temporary directory."""
    try:
        shutil.rmtree(path)
    except Exception as e:
        logger.warning(f"Failed to cleanup temp dir {path}: {e}")

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
    storage = get_storage()
    temp_dir = create_temp_dir()
    
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename, ALLOWED_EXCEL):
            return jsonify({'error': 'Invalid file type. Only Excel files allowed.'}), 400
        
        # Save uploaded file to temp
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        
        input_path = temp_dir / unique_filename
        file.save(str(input_path))
        
        # Upload original to S3
        storage.upload_file(input_path, f'uploads/{unique_filename}')
        
        # Get options
        sheets = request.form.get('sheets', '')
        sheet_list = [s.strip() for s in sheets.split(',') if s.strip()] if sheets else None
        
        # Create output directory
        output_dir = temp_dir / 'output'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Run parser
        pipeline = ExcelToJsonPipeline()
        output_files = pipeline.process_file(
            input_file=input_path,
            output_mode="multiple",
            output_dir=output_dir,
            sheets=sheet_list
        )
        
        # Upload outputs to S3
        output_names = []
        s3_prefix = f"indexes/{timestamp}"
        for f in output_files:
            s3_key = f"{s3_prefix}/{f.name}"
            storage.upload_file(f, s3_key)
            output_names.append(f.name)
        
        return jsonify({
            'success': True,
            'message': f'Successfully parsed {len(output_files)} sheet(s)',
            'input_file': unique_filename,
            'output_files': output_names,
            'output_dir': s3_prefix
        })
        
    except Exception as e:
        logger.error(f"Parse error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        cleanup_temp_dir(temp_dir)

@app.route('/index', methods=['GET'])
def index_page():
    """Index page - JSON to Vector Store."""
    storage = get_storage()
    settings = get_settings()
    
    # List available JSON 'directories' in S3 (by grouping prefixes)
    json_dirs = []
    
    try:
        # We assume structure indexes/TIMESTAMP/file.json
        # So we look for "folders" under indexes/
        # S3 listing is flat, so we list indexes/ and group
        # This is a bit expensive if many files, but okay for prototype
        
        # Actually storage.list_files returns files. We need to find unique 'folders'
        # A better way for S3 is to use delimiter, but our list_files wrapper simplifies 'Contents'
        # Let's just list everything in 'indexes/' and unique the logical parent
        
        all_files = storage.list_files('indexes/')
        
        groups = {}
        for f in all_files:
            # key is like indexes/20230101_120000/sheet.json
            parts = f['key'].split('/')
            if len(parts) >= 3:
                folder_name = parts[1] # timestamp folder
                if folder_name not in groups:
                    groups[folder_name] = {'count': 0, 'path': f"indexes/{folder_name}"}
                groups[folder_name]['count'] += 1

        for name, info in groups.items():
            json_dirs.append({
                'name': name,
                'path': info['path'], # Used as ID
                'json_count': info['count']
            })
            
        # Sort by name (timestamp) desc
        json_dirs.sort(key=lambda x: x['name'], reverse=True)
        
    except Exception as e:
        logger.error(f"Error listing index directories: {e}")
    
    return render_template('index_vectors.html', json_dirs=json_dirs, settings=settings)

@app.route('/api/index', methods=['POST'])
@async_route
async def api_index():
    """API endpoint for indexing JSON to vector store."""
    storage = get_storage()
    temp_dir = create_temp_dir()
    
    try:
        data = request.get_json()
        input_path_str = data.get('input_path') # This is the S3 prefix, e.g. "indexes/2025..."
        namespace = data.get('namespace', '')
        create_new = data.get('create_index', False)
        
        if not input_path_str:
            return jsonify({'error': 'No input path provided'}), 400
            
        settings, openai_async, embeddings_service, vector_store_service = get_services()
        
        # Download files from S3 to temp
        # input_path_str is like 'indexes/TIMESTMAP'
        # We need to download all files in that prefix
        local_input_dir = temp_dir / 'json_input'
        local_input_dir.mkdir()
        
        files = storage.list_files(input_path_str + '/')
        if not files:
             return jsonify({'error': f'No files found in {input_path_str}'}), 400
             
        for f in files:
             storage.download_file(f['key'], local_input_dir / f['name'])
        
        # Create or connect to index
        if create_new:
            await vector_store_service.create_index(
                dimension=settings.s3_vectors_dimension,
                metric='cosine'
            )
        else:
            vector_store_service.get_index()
        
        # Process JSON files
        processor = JSONProcessor()
        documents = processor.process_directory(local_input_dir)
        
        if not documents:
            return jsonify({'error': 'No documents found to index'}), 400
        
        # Index documents
        indexer = VectorStoreIndexer(embeddings_service, vector_store_service)
        result = await indexer.index_documents(
            documents,
            embedding_batch_size=settings.batch_size,
            upsert_batch_size=settings.batch_size,
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
    finally:
        cleanup_temp_dir(temp_dir)

@app.route('/fill', methods=['GET'])
def fill_page():
    """Fill page - Rate filling interface."""
    settings = get_settings()
    return render_template('fill.html', settings=settings)

@app.route('/api/fill', methods=['POST'])
@async_route
async def api_fill():
    """API endpoint for filling rates in Excel."""
    storage = get_storage()
    temp_dir = create_temp_dir()
    
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
        
        input_path = temp_dir / unique_filename
        file.save(str(input_path))
        
        # Upload to S3 (optional, but good for record)
        storage.upload_file(input_path, f'uploads/{unique_filename}')
        
        # Get options
        sheet_name = request.form.get('sheet_name') or None
        namespace = request.form.get('namespace', '')
        threshold = request.form.get('threshold')
        threshold = float(threshold) if threshold else None
        top_k = request.form.get('top_k')
        top_k = int(top_k) if top_k else None
        
        settings, openai_async, embeddings_service, vector_store_service = get_services()
        
        # Apply defaults
        namespace = namespace if namespace else ""
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
        output_path = temp_dir / output_filename
        
        # Process file
        result = await pipeline.process_file(
            input_file=input_path,
            sheet_name=sheet_name,
            output_file=output_path,
            namespace=namespace,
            workers=settings.max_workers
        )
        
        # Upload result to S3
        s3_key_fill = f'fills/{output_filename}'
        storage.upload_file(output_path, s3_key_fill)
        
        # Upload summary if exists
        summary_local = result.get('summary_file')
        if summary_local:
             summary_path = Path(summary_local)
             storage.upload_file(summary_path, f'fills/{summary_path.name}')
        
        report = result['report']
        
        return jsonify({
            'success': True,
            'message': 'Rate filling complete',
            'input_file': unique_filename,
            'output_file': s3_key_fill, # Return key for download
            'summary_file': Path(summary_local).name if summary_local else None,
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
    finally:
        cleanup_temp_dir(temp_dir)

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
        vector_store = get_vector_store()
        index_stats = vector_store.get_stats()
    except Exception as e:
        logger.warning(f"Could not get index stats: {e}")
    
    return render_template('settings.html', settings=settings, index_stats=index_stats)

@app.route('/download/<path:key>')
def download_file(key: str):
    """
    Download a file from storage.
    Note: Flask converts the path 'fills/foo.xlsx' to key='fills/foo.xlsx'.
    We redirect to S3 presigned URL.
    """
    storage = get_storage()
    try:
        # Check if local or s3
        if storage.type == 's3':
             url = storage.get_presigned_url(key)
             if url:
                 return redirect(url)
             else:
                 return jsonify({'error': 'Could not generate download link'}), 500
        else:
            # Local fallback
             # Determine folder based on key prefix
             # key might be 'fills/output.xlsx' or just 'output.xlsx'
             # The existing code expected /download/FOLDER/FILENAME
             # We should support the key directly
             data_dir = storage.settings.project_root / 'app' / 'data'
             file_path = data_dir / key
             if file_path.exists():
                 return send_file(str(file_path), as_attachment=True)
             return jsonify({'error': 'File not found'}), 404
             
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<folder>')
def list_files(folder: str):
    """List files in a folder (uploads, fills, indexes)."""
    storage = get_storage()
    try:
        files = storage.list_files(folder + '/')
        return jsonify({'files': files})
    except Exception as e:
        logger.error(f"List files error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/json-files')
def list_json_files():
    """List all JSON files available for indexing."""
    # This might be tricky if we want to list recursively
    # But for now, we rely on the grouping in /index page
    # This API was used if the parsing returned individual files, not needed much now
    storage = get_storage()
    try:
        files = storage.list_files('indexes/')
        # Filter for .json
        json_files = [f for f in files if f['name'].endswith('.json')]
        return jsonify({'files': json_files})
    except Exception as e:
         return jsonify({'error': str(e)}), 500

@app.route('/api/index-stats')
def api_index_stats():
    """Get vector store index statistics."""
    try:
        vector_store = get_vector_store()
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
    """Delete a file."""
    storage = get_storage()
    try:
        data = request.get_json()
        folder = data.get('folder') # 'uploads', 'fills'
        filename = data.get('filename')
        
        if not folder or not filename:
            return jsonify({'error': 'Folder and filename are required'}), 400
            
        key = f"{folder}/{filename}"
        if storage.delete_file(key):
             return jsonify({'success': True, 'message': f'Deleted {key}'})
        else:
             return jsonify({'error': 'Failed to delete file'}), 500
        
    except Exception as e:
        logger.error(f"Delete file error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete-all', methods=['POST'])
def api_delete_all():
    """Delete all files in a folder."""
    # S3 doesn't have a cheap delete-all, we'd have to list and delete.
    # Be careful with this.
    storage = get_storage()
    try:
        data = request.get_json()
        folder = data.get('folder')
        if not folder: return jsonify({'error': 'Folder required'}), 400
        
        files = storage.list_files(folder + '/')
        count = 0
        for f in files:
            storage.delete_file(f['key'])
            count += 1
            
        return jsonify({'success': True, 'message': f'Deleted {count} items'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error='Page not found', code=404), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error='Internal server error', code=500), 500

# ==================== Main ====================

def run_app(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
    """Run the Flask application."""
    logger.info(f"Starting Almabani GUI on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)

if __name__ == '__main__':
    run_app(debug=True)
