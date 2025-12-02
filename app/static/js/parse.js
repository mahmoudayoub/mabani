/**
 * Parse Page JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('parse-form');
    const fileInput = document.getElementById('excel-file');
    const dropZone = document.querySelector('.upload-area');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    const removeFile = document.getElementById('remove-file');
    const submitBtn = document.getElementById('submit-btn');
    const progressSection = document.getElementById('progress-section');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const resultSection = document.getElementById('result-section');
    const resultContent = document.getElementById('result-content');
    
    // Drag and drop handlers
    if (dropZone) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });
        
        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.add('dragover');
            }, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.remove('dragover');
            }, false);
        });
        
        dropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                handleFileSelect(files[0]);
            }
        }, false);
    }
    
    // File input change
    if (fileInput) {
        fileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                handleFileSelect(this.files[0]);
            }
        });
    }
    
    // Handle file selection
    function handleFileSelect(file) {
        // Check file type
        const validTypes = [
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel'
        ];
        const validExtensions = ['.xlsx', '.xls'];
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        
        if (!validTypes.includes(file.type) && !validExtensions.includes(ext)) {
            showError('Please select a valid Excel file (.xlsx or .xls)');
            fileInput.value = '';
            return;
        }
        
        // Show file info
        if (fileName) fileName.textContent = file.name;
        if (fileSize) fileSize.textContent = formatFileSize(file.size);
        if (fileInfo) fileInfo.classList.remove('hidden');
        if (dropZone) dropZone.style.display = 'none';
        if (submitBtn) submitBtn.disabled = false;
    }
    
    // Remove file
    if (removeFile) {
        removeFile.addEventListener('click', function() {
            fileInput.value = '';
            if (fileInfo) fileInfo.classList.add('hidden');
            if (dropZone) dropZone.style.display = 'flex';
            if (submitBtn) submitBtn.disabled = true;
        });
    }
    
    // Form submission
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(form);
            
            // Show progress
            if (progressSection) progressSection.classList.remove('hidden');
            if (resultSection) resultSection.classList.add('hidden');
            if (submitBtn) submitBtn.disabled = true;
            
            try {
                // Upload file
                updateProgress(10, 'Uploading file...');
                
                const response = await fetch('/api/parse', {
                    method: 'POST',
                    body: formData
                });
                
                updateProgress(30, 'Processing Excel file...');
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to parse file');
                }
                
                updateProgress(60, 'Building hierarchy...');
                
                const result = await response.json();
                
                updateProgress(100, 'Complete!');
                
                // Show result
                setTimeout(() => {
                    showResult(result);
                }, 500);
                
            } catch (error) {
                showError(error.message);
                if (progressSection) progressSection.classList.add('hidden');
                if (submitBtn) submitBtn.disabled = false;
            }
        });
    }
    
    function updateProgress(percent, text) {
        if (progressBar) {
            progressBar.style.width = percent + '%';
            progressBar.textContent = percent + '%';
        }
        if (progressText) progressText.textContent = text;
    }
    
    function showResult(result) {
        if (progressSection) progressSection.classList.add('hidden');
        if (resultSection) resultSection.classList.remove('hidden');
        
        if (resultContent) {
            let html = '<div class="result-summary">';
            html += `<div class="stat-item"><span class="stat-label">Output Files:</span> <span class="stat-value">${result.output_files?.length || 0}</span></div>`;
            html += `<div class="stat-item"><span class="stat-label">Processing Time:</span> <span class="stat-value">${result.processing_time || 'N/A'}</span></div>`;
            html += '</div>';
            
            if (result.output_files && result.output_files.length > 0) {
                html += '<h4>Generated Files:</h4><ul class="file-list">';
                result.output_files.forEach(file => {
                    html += `<li><i class="fas fa-file-code"></i> ${file}</li>`;
                });
                html += '</ul>';
            }
            
            if (result.download_url) {
                html += `<a href="${result.download_url}" class="btn btn-success"><i class="fas fa-download"></i> Download JSON</a>`;
            }
            
            resultContent.innerHTML = html;
        }
        
        // Reset form for new upload
        if (submitBtn) submitBtn.disabled = false;
    }
});
