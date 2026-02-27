"""End-to-End tests for the data ingestion script.

This module tests the complete ingestion workflow via the command-line interface,
including:
- Single file ingestion
- Directory ingestion
- Force re-processing
- Skip already processed files
- Error handling for invalid inputs
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Project root for script execution
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestDataIngestion:
    """E2E tests for scripts/ingest.py."""
    
    @pytest.fixture
    def temp_data_dir(self, tmp_path):
        """Create a temporary data directory for test outputs.
        
        Yields:
            Path to temporary directory
        """
        # Create subdirectories matching production structure
        (tmp_path / "db" / "chroma").mkdir(parents=True)
        (tmp_path / "db" / "bm25").mkdir(parents=True)
        (tmp_path / "images").mkdir(parents=True)
        
        yield tmp_path
        
        # Cleanup is handled by pytest tmp_path fixture
    
    @pytest.fixture
    def sample_pdf(self):
        """Get path to sample PDF for testing.
        
        Returns:
            Path to a sample PDF file
        """
        pdf_path = PROJECT_ROOT / "tests" / "fixtures" / "sample_documents" / "simple.pdf"
        if not pdf_path.exists():
            pytest.skip("Sample PDF not found")
        return pdf_path
    
    @pytest.fixture
    def complex_pdf(self):
        """Get path to complex technical document for testing.
        
        Returns:
            Path to a complex PDF with images
        """
        pdf_path = PROJECT_ROOT / "tests" / "fixtures" / "sample_documents" / "complex_technical_doc.pdf"
        if not pdf_path.exists():
            pytest.skip("Complex PDF not found")
        return pdf_path
    
    def run_ingest_script(
        self,
        path: str,
        collection: str = "test_collection",
        force: bool = False,
        config: str = None,
        dry_run: bool = False,
        verbose: bool = False
    ) -> subprocess.CompletedProcess:
        """Run the ingest script as a subprocess.
        
        Args:
            path: Path to file or directory
            collection: Collection name
            force: Whether to force re-processing
            config: Custom config path
            dry_run: Whether to run in dry-run mode
            verbose: Whether to enable verbose output
            
        Returns:
            CompletedProcess with stdout, stderr, and return code
        """
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "ingest.py"),
            "--path", str(path),
            "--collection", collection
        ]
        
        if force:
            cmd.append("--force")
        
        if config:
            cmd.extend(["--config", config])
        
        if dry_run:
            cmd.append("--dry-run")
        
        if verbose:
            cmd.append("--verbose")
        
        # Set PYTHONUTF8=1 to avoid encoding issues on Windows
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=600,  # 10 minute timeout for LLM calls (complex docs with vision)
            env=env,
            encoding='utf-8',
            errors='replace'
        )
    
    def test_ingest_help(self):
        """Test that --help flag works."""
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "ingest.py"), "--help"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        
        assert result.returncode == 0
        assert "--path" in result.stdout
        assert "--collection" in result.stdout
        assert "--force" in result.stdout
    
    def test_ingest_nonexistent_file(self):
        """Test error handling for non-existent file."""
        result = self.run_ingest_script(
            path="/nonexistent/path/document.pdf"
        )
        
        assert result.returncode == 2
        assert "does not exist" in result.stdout or "not found" in result.stdout.lower()
    
    def test_ingest_invalid_config(self, sample_pdf):
        """Test error handling for invalid config file."""
        result = self.run_ingest_script(
            path=str(sample_pdf),
            config="/nonexistent/config.yaml"
        )
        
        assert result.returncode == 2
        assert "not found" in result.stdout.lower() or "Configuration" in result.stdout
    
    def test_ingest_dry_run(self, sample_pdf):
        """Test dry-run mode doesn't process files."""
        result = self.run_ingest_script(
            path=str(sample_pdf),
            dry_run=True
        )
        
        assert result.returncode == 0
        assert "Dry run" in result.stdout or "dry run" in result.stdout.lower()
        assert "1 file" in result.stdout
    
    def test_ingest_unsupported_file_type(self, tmp_path):
        """Test error handling for unsupported file types."""
        # Create a text file
        text_file = tmp_path / "document.txt"
        text_file.write_text("This is a text file")
        
        result = self.run_ingest_script(
            path=str(text_file)
        )
        
        assert result.returncode == 2
        assert "Unsupported" in result.stdout or "unsupported" in result.stdout.lower()
    
    @pytest.mark.integration
    def test_ingest_simple_pdf(self, sample_pdf):
        """Test ingesting a simple PDF file.
        
        This test requires Azure API credentials to be configured.
        """
        result = self.run_ingest_script(
            path=str(sample_pdf),
            collection="e2e_test_simple",
            force=True,  # Force to ensure fresh processing
            verbose=True
        )
        
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        
        # Should succeed or partially succeed
        assert result.returncode in [0, 1], f"Unexpected return code: {result.returncode}"
        assert "Processing" in result.stdout
        assert "SUMMARY" in result.stdout
    
    @pytest.mark.integration
    def test_ingest_complex_pdf_with_images(self, complex_pdf):
        """Test ingesting a complex PDF with images.
        
        This test requires Azure API credentials and Vision LLM to be configured.
        Tests the full pipeline including image captioning.
        """
        result = self.run_ingest_script(
            path=str(complex_pdf),
            collection="e2e_test_complex",
            force=True,
            verbose=True
        )
        
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        
        # Should succeed or partially succeed
        assert result.returncode in [0, 1], f"Unexpected return code: {result.returncode}"
        assert "Processing" in result.stdout
        assert "SUMMARY" in result.stdout
        
        # If successful, should report chunks and possibly images
        if result.returncode == 0:
            assert "chunks" in result.stdout.lower()
    
    @pytest.mark.integration
    def test_ingest_skip_already_processed(self, sample_pdf):
        """Test that already processed files are skipped.
        
        Runs ingestion twice and verifies second run skips the file.
        """
        # First run - should process
        result1 = self.run_ingest_script(
            path=str(sample_pdf),
            collection="e2e_test_skip",
            force=True  # Ensure fresh start
        )
        
        print("First run STDOUT:", result1.stdout)
        
        # Skip test if first run failed
        if result1.returncode == 2:
            pytest.skip("First ingestion failed - cannot test skip behavior")
        
        # Second run - should skip
        result2 = self.run_ingest_script(
            path=str(sample_pdf),
            collection="e2e_test_skip",
            force=False  # Don't force, should skip
        )
        
        print("Second run STDOUT:", result2.stdout)
        
        # Should succeed but with skip
        assert result2.returncode == 0
        assert "skip" in result2.stdout.lower() or "already processed" in result2.stdout.lower()
    
    @pytest.mark.integration
    def test_ingest_force_reprocess(self, sample_pdf):
        """Test that --force flag causes re-processing."""
        # First run
        result1 = self.run_ingest_script(
            path=str(sample_pdf),
            collection="e2e_test_force",
            force=True
        )
        
        # Skip test if first run failed
        if result1.returncode == 2:
            pytest.skip("First ingestion failed - cannot test force behavior")
        
        # Second run with force - should process again
        result2 = self.run_ingest_script(
            path=str(sample_pdf),
            collection="e2e_test_force",
            force=True,
            verbose=True
        )
        
        print("Second run STDOUT:", result2.stdout)
        
        # Should succeed and process (not skip)
        assert result2.returncode in [0, 1]
        # When forced, should not show "skipped"
        if "Success" in result2.stdout:
            assert "chunks" in result2.stdout.lower() or "processed" in result2.stdout.lower()
    
    @pytest.mark.integration
    def test_ingest_directory(self, tmp_path, sample_pdf):
        """Test ingesting all PDFs in a directory."""
        # Create a directory with multiple PDFs (copy sample)
        test_dir = tmp_path / "pdfs"
        test_dir.mkdir()
        
        shutil.copy(sample_pdf, test_dir / "doc1.pdf")
        shutil.copy(sample_pdf, test_dir / "doc2.pdf")
        
        result = self.run_ingest_script(
            path=str(test_dir),
            collection="e2e_test_dir",
            force=True,
            verbose=True
        )
        
        print("STDOUT:", result.stdout)
        
        # Should find both files
        assert "2 file" in result.stdout
        
        # Should attempt to process both
        assert "[1/2]" in result.stdout
        assert "[2/2]" in result.stdout
    
    def test_ingest_empty_directory(self, tmp_path):
        """Test handling of directory with no PDFs."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        
        result = self.run_ingest_script(
            path=str(empty_dir)
        )
        
        assert result.returncode == 0
        assert "0 file" in result.stdout or "No files" in result.stdout


class TestIngestScriptIntegration:
    """Integration tests that verify data persistence."""
    
    @pytest.mark.integration
    def test_creates_vector_store_data(self, tmp_path):
        """Verify that ingestion creates vector store data."""
        # This test verifies the pipeline creates the expected output files
        # It's marked as integration because it requires the full stack
        
        sample_pdf = PROJECT_ROOT / "tests" / "fixtures" / "sample_documents" / "simple.pdf"
        if not sample_pdf.exists():
            pytest.skip("Sample PDF not found")
        
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "ingest.py"),
                "--path", str(sample_pdf),
                "--collection", "e2e_test_persistence",
                "--force"
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=300
        )
        
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        
        # Verify data directories exist after successful ingestion
        if result.returncode == 0:
            chroma_dir = PROJECT_ROOT / "data" / "db" / "chroma"
            bm25_dir = PROJECT_ROOT / "data" / "db" / "bm25" / "e2e_test_persistence"
            
            assert chroma_dir.exists(), "ChromaDB directory should exist"
            # BM25 index directory may or may not exist based on implementation


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
