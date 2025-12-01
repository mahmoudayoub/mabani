"""
Unified CLI for Almabani BOQ Management System.
Provides commands for parsing, indexing, and rate filling.
"""
import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich import print as rprint
import logging

from almabani.config.settings import get_settings, get_openai_client, get_pinecone_client
from almabani.config.logging_config import setup_logging
from almabani.parsers.pipeline import ExcelToJsonPipeline
from almabani.vectorstore.indexer import JSONProcessor, VectorStoreIndexer
from almabani.core.embeddings import EmbeddingsService
from almabani.core.vector_store import VectorStoreService
from almabani.rate_matcher.matcher import RateMatcher
from almabani.rate_matcher.pipeline import RateFillerPipeline

app = typer.Typer(help="Almabani BOQ Management System")
console = Console()


@app.command()
def parse(
    input_file: Path = typer.Argument(..., help="Excel BOQ file to parse"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    mode: str = typer.Option("multiple", "--mode", "-m", help="Output mode: 'single' or 'multiple'"),
    sheets: Optional[str] = typer.Option(None, "--sheets", "-s", help="Comma-separated sheet names"),
    log_file: Optional[Path] = typer.Option(None, "--log", "-l", help="Log file path")
):
    """📄 Parse Excel BOQ file into hierarchical JSON."""
    console.print(Panel.fit(
        f"[bold cyan]Excel to JSON Parser[/bold cyan]\n"
        f"Input: {input_file}\n"
        f"Mode: {mode}",
        border_style="cyan"
    ))
    
    # Setup logging
    setup_logging(log_file=log_file)
    logger = logging.getLogger(__name__)
    
    try:
        # Parse sheets list if provided
        sheet_list = [s.strip() for s in sheets.split(',')] if sheets else None
        
        # Create pipeline
        pipeline = ExcelToJsonPipeline()
        
        # Process file
        output_files = pipeline.process_file(
            input_file=input_file,
            output_mode=mode,
            output_dir=output_dir,
            sheets=sheet_list
        )
        
        console.print(f"\n[green]✓[/green] Generated {len(output_files)} JSON file(s):")
        for f in output_files:
            console.print(f"  • {f}")
        
    except Exception as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        logger.error(f"Parse command failed: {e}", exc_info=True)
        raise typer.Exit(1)


@app.command()
def index(
    input_path: Path = typer.Argument(..., help="JSON file or directory to index"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Pinecone namespace"),
    batch_size: Optional[int] = typer.Option(None, "--batch-size", "-b", help="Embedding batch size"),
    upsert_batch_size: Optional[int] = typer.Option(None, "--upsert-batch-size", "-u", help="Pinecone upsert batch size"),
    create_index: bool = typer.Option(False, "--create", "-c", help="Create index if doesn't exist"),
    workers: Optional[int] = typer.Option(None, "--workers", "-w", help="Number of parallel workers"),
    log_file: Optional[Path] = typer.Option(None, "--log", "-l", help="Log file path")
):
    """📊 Index JSON BOQ data into vector store."""
    console.print(Panel.fit(
        f"[bold magenta]Vector Store Indexer[/bold magenta]\n"
        f"Input: {input_path}\n"
        f"Namespace: {namespace or 'default'}",
        border_style="magenta"
    ))
    
    # Setup logging
    setup_logging(log_file=log_file)
    logger = logging.getLogger(__name__)
    
    try:
        # Get settings and clients
        settings = get_settings()
        openai_client = get_openai_client()
        pinecone_client = get_pinecone_client()
        
        # Apply defaults from settings when CLI values are not provided
        namespace = namespace if namespace is not None else (settings.pinecone_namespace or "")
        batch_size = batch_size if batch_size is not None else settings.batch_size
        upsert_batch_size = upsert_batch_size if upsert_batch_size is not None else settings.pinecone_batch_size
        workers = workers if workers is not None else settings.max_workers
        
        # Create services
        embeddings_service = EmbeddingsService(
            client=openai_client,
            model=settings.openai_embedding_model,
            batch_size=batch_size,
            max_workers=workers
        )
        
        vector_store_service = VectorStoreService(
            client=pinecone_client,
            index_name=settings.pinecone_index_name,
            environment=settings.pinecone_environment
        )
        
        # Create or connect to index
        if create_index:
            vector_store_service.create_index(
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
            console.print("[yellow]⚠[/yellow] No documents found to index")
            return
        
        # Index documents
        indexer = VectorStoreIndexer(embeddings_service, vector_store_service)
        result = indexer.index_documents(
            documents,
            embedding_batch_size=batch_size,
            upsert_batch_size=upsert_batch_size,
            namespace=namespace,
            max_workers=workers
        )
        
        console.print(f"\n[green]✓[/green] Indexing complete!")
        console.print(f"  • Uploaded: {result['uploaded_count']} vectors")
        console.print(f"  • Total in index: {result['total_vectors_in_index']}")
        
    except Exception as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        logger.error(f"Index command failed: {e}", exc_info=True)
        raise typer.Exit(1)


@app.command()
def fill(
    input_file: Path = typer.Argument(..., help="Excel BOQ file to fill"),
    sheet_name: Optional[str] = typer.Argument(None, help="Sheet name to process (defaults to first sheet)"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output Excel file"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Pinecone namespace"),
    threshold: Optional[float] = typer.Option(None, "--threshold", "-t", help="Similarity threshold"),
    top_k: Optional[int] = typer.Option(None, "--top-k", "-k", help="Number of candidates"),
    workers: Optional[int] = typer.Option(None, "--workers", "-w", help="Number of parallel workers"),
    log_file: Optional[Path] = typer.Option(None, "--log", "-l", help="Log file path")
):
    """💰 Fill missing rates in Excel BOQ using LLM matching."""
    console.print(Panel.fit(
        f"[bold green]Rate Filler[/bold green]\n"
        f"Input: {input_file}\n"
        f"Sheet: {sheet_name or 'first sheet'}\n"
        f"Threshold: {threshold}",
        border_style="green"
    ))
    
    # Setup logging
    setup_logging(log_file=log_file)
    logger = logging.getLogger(__name__)
    
    try:
        # Get settings and clients
        settings = get_settings()
        openai_client = get_openai_client()
        pinecone_client = get_pinecone_client()
        
        # Create services
        namespace = namespace if namespace is not None else (settings.pinecone_namespace or "")
        threshold = threshold if threshold is not None else settings.similarity_threshold
        top_k = top_k if top_k is not None else settings.top_k
        workers = workers if workers is not None else settings.max_workers
        
        embeddings_service = EmbeddingsService(
            client=openai_client,
            model=settings.openai_embedding_model
        )
        
        vector_store_service = VectorStoreService(
            client=pinecone_client,
            index_name=settings.pinecone_index_name,
            environment=settings.pinecone_environment
        )
        
        # Create rate matcher
        rate_matcher = RateMatcher(
            openai_client=openai_client,
            embeddings_service=embeddings_service,
            vector_store_service=vector_store_service,
            similarity_threshold=threshold,
            top_k=top_k,
            model=settings.openai_chat_model,
            verbose_logging=True
        )
        
        # Create pipeline
        pipeline = RateFillerPipeline(rate_matcher)
        
        # Process file
        result = pipeline.process_file(
            input_file=input_file,
            sheet_name=sheet_name,
            output_file=output_file,
            namespace=namespace,
            workers=workers
        )
        
        # Display report
        report = result['report']
        console.print(f"\n[green]✓[/green] Processing complete!")
        console.print(f"  • Processed: {report['processed_items']}/{report['total_items']}")
        console.print(f"  • Exact matches: {report['exact_matches']}")
        console.print(f"  • Expert matches: {report['expert_matches']}")
        console.print(f"  • Estimates: {report['estimates']}")
        console.print(f"  • No matches: {report['no_matches']}")
        console.print(f"  • Errors: {report['errors']}")
        console.print(f"  • Output: {result['output_file']}")
        
    except Exception as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        logger.error(f"Fill command failed: {e}", exc_info=True)
        raise typer.Exit(1)


@app.command()
def query(
    search_text: str = typer.Argument(..., help="Text to search for"),
    namespace: Optional[str] = typer.Option(None, "--namespace", "-n", help="Pinecone namespace"),
    top_k: Optional[int] = typer.Option(None, "--top-k", "-k", help="Number of results"),
    threshold: Optional[float] = typer.Option(None, "--threshold", "-t", help="Minimum similarity score")
):
    """🔍 Query the vector store for similar items."""
    console.print(Panel.fit(
        f"[bold blue]Vector Store Query[/bold blue]\n"
        f"Query: {search_text}\n"
        f"Top-K: {top_k}",
        border_style="blue"
    ))
    
    try:
        # Get settings and clients
        settings = get_settings()
        openai_client = get_openai_client()
        pinecone_client = get_pinecone_client()
        
        namespace = namespace if namespace is not None else (settings.pinecone_namespace or "")
        top_k = top_k if top_k is not None else settings.top_k
        threshold = threshold if threshold is not None else settings.similarity_threshold
        
        # Create services
        embeddings_service = EmbeddingsService(
            client=openai_client,
            model=settings.openai_embedding_model
        )
        
        vector_store_service = VectorStoreService(
            client=pinecone_client,
            index_name=settings.pinecone_index_name,
            environment=settings.pinecone_environment
        )
        
        # Generate embedding
        query_embedding = embeddings_service.generate_embedding(search_text)
        
        # Search
        results = vector_store_service.search(
            query_embedding=query_embedding,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True
        )
        
        # Display results
        console.print(f"\n[cyan]Found {len(results)} results:[/cyan]\n")
        
        for i, result in enumerate(results, 1):
            if result['score'] >= threshold:
                console.print(f"[bold]{i}. Score: {result['score']:.3f}[/bold]")
                console.print(f"   {result['text']}")
                metadata = result['metadata']
                if 'unit' in metadata and metadata['unit']:
                    console.print(f"   Unit: {metadata['unit']}")
                if 'rate' in metadata and metadata['rate']:
                    console.print(f"   Rate: {metadata['rate']}")
                if 'sheet_name' in metadata:
                    console.print(f"   Source: {metadata['sheet_name']}")
                console.print()
        
    except Exception as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def delete_index(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt")
):
    """🗑️  Delete the entire Pinecone index."""
    settings = get_settings()
    
    console.print(Panel.fit(
        f"[bold red]⚠️  WARNING: DELETE INDEX[/bold red]\n"
        f"Index: {settings.pinecone_index_name}\n"
        f"This will permanently delete ALL vectors!",
        border_style="red"
    ))
    
    if not force:
        response = typer.confirm(f"\nDelete index '{settings.pinecone_index_name}'?", default=False)
        if not response:
            console.print("[yellow]❌ Cancelled by user[/yellow]")
            raise typer.Exit(0)
    
    try:
        pc = get_pinecone_client()
        existing_indexes = pc.list_indexes()
        index_names = [idx.name for idx in existing_indexes]
        
        if settings.pinecone_index_name in index_names:
            console.print(f"\n[red]🗑️  Deleting index '{settings.pinecone_index_name}'...[/red]")
            pc.delete_index(settings.pinecone_index_name)
            console.print(f"[green]✓ Index '{settings.pinecone_index_name}' deleted successfully![/green]")
            console.print("\n[yellow]Run 'almabani index' to rebuild the vector database[/yellow]")
        else:
            console.print(f"[yellow]ℹ️  Index '{settings.pinecone_index_name}' does not exist[/yellow]")
        
    except Exception as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def delete_sheet(
    sheet_name: str = typer.Argument(..., help="Sheet name to delete (e.g., '1-master_no_ur')"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt")
):
    """🗑️  Delete all vectors from a specific sheet."""
    settings = get_settings()
    
    console.print(Panel.fit(
        f"[bold yellow]⚠️  WARNING: DELETE SHEET[/bold yellow]\n"
        f"Sheet: {sheet_name}\n"
        f"Index: {settings.pinecone_index_name}\n"
        f"This will delete all vectors from this sheet!",
        border_style="yellow"
    ))
    
    if not force:
        response = typer.confirm(f"\nDelete all vectors from sheet '{sheet_name}'?", default=False)
        if not response:
            console.print("[yellow]❌ Cancelled by user[/yellow]")
            raise typer.Exit(0)
    
    try:
        pc = get_pinecone_client()
        index = pc.Index(settings.pinecone_index_name)
        
        console.print(f"\n[cyan]Finding vectors for sheet '{sheet_name}'...[/cyan]")
        total_for_sheet = None
        stats_supported = True
        try:
            stats = index.describe_index_stats(filter={"sheet_name": {"$eq": sheet_name}})
            total_for_sheet = stats.get('namespaces', {}).get('', {}).get('vector_count', 0)
        except Exception:
            stats_supported = False
            console.print("[yellow]ℹ️  This index cannot report counts by metadata filter; proceeding without a pre-check.[/yellow]")
        
        if stats_supported and total_for_sheet == 0:
            console.print(f"[yellow]ℹ️  No vectors found for sheet '{sheet_name}'. Nothing to delete.[/yellow]")
            raise typer.Exit(0)
        
        try:
            index.delete(filter={"sheet_name": {"$eq": sheet_name}})
        except Exception as del_err:
            console.print(f"[red]✗ Delete failed:[/red] {del_err}")
            raise typer.Exit(1)
        
        if stats_supported and total_for_sheet is not None:
            console.print(f"[green]✓ Deleted {total_for_sheet} vector(s) from sheet '{sheet_name}'.[/green]")
        else:
            console.print(f"[green]✓ Delete request sent for sheet '{sheet_name}'.[/green] [yellow](Count verification not supported by this index type.)[/yellow]")
        
        console.print(f"\n[yellow]Run 'almabani index' with the sheet's JSON to re-index it[/yellow]")
        
    except Exception as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def version():
    """📌 Show version information."""
    from almabani import __version__
    console.print(f"[bold cyan]Almabani BOQ Management System[/bold cyan]")
    console.print(f"Version: {__version__}")


if __name__ == "__main__":
    app()
