/**
 * Fill Page JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('fill-form');
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
    const statusList = document.getElementById('status-list');
    const resultSection = document.getElementById('result-section');
    const resultContent = document.getElementById('result-content');
    
    let eventSource = null;
    
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
        const validExtensions = ['.xlsx', '.xls'];
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        
        if (!validExtensions.includes(ext)) {
            showError('Please select a valid Excel file (.xlsx or .xls)');
            fileInput.value = '';
            return;
        }
        
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
            if (statusList) statusList.innerHTML = '';
            if (submitBtn) submitBtn.disabled = true;
            
            try {
                addStatus('Uploading file...', 'pending');
                updateProgress(5, 'Uploading...');
                
                const response = await fetch('/api/fill', {
                    method: 'POST',
                    body: formData
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to start fill process');
                }
                
                const { task_id } = await response.json();
                updateStatus(0, 'complete');
                addStatus('Processing started...', 'pending');
                
                // Start polling for updates
                pollFillProgress(task_id);
                
            } catch (error) {
                showError(error.message);
                if (progressSection) progressSection.classList.add('hidden');
                if (submitBtn) submitBtn.disabled = false;
            }
        });
    }
    
    async function pollFillProgress(taskId) {
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/task/${taskId}`);
                const task = await response.json();
                
                if (task.status === 'completed') {
                    clearInterval(pollInterval);
                    updateProgress(100, 'Complete!');
                    updateStatus(-1, 'complete');
                    setTimeout(() => showResult(task.result), 500);
                } else if (task.status === 'failed') {
                    clearInterval(pollInterval);
                    throw new Error(task.error || 'Fill process failed');
                } else {
                    // Update progress
                    const progress = task.progress || 0;
                    updateProgress(progress, task.message || 'Processing...');
                    
                    // Add status updates
                    if (task.message && task.message !== getLastStatus()) {
                        updateStatus(-1, 'complete');
                        addStatus(task.message, 'pending');
                    }
                }
            } catch (error) {
                clearInterval(pollInterval);
                showError(error.message);
                if (progressSection) progressSection.classList.add('hidden');
                if (submitBtn) submitBtn.disabled = false;
            }
        }, 2000);
    }
    
    function addStatus(text, status) {
        if (!statusList) return;
        
        const item = document.createElement('li');
        item.className = `status-item ${status}`;
        item.innerHTML = `
            <span class="status-icon">
                ${status === 'pending' ? '<i class="fas fa-spinner fa-spin"></i>' : 
                  status === 'complete' ? '<i class="fas fa-check"></i>' : 
                  '<i class="fas fa-times"></i>'}
            </span>
            <span class="status-text">${text}</span>
        `;
        statusList.appendChild(item);
        statusList.scrollTop = statusList.scrollHeight;
    }
    
    function updateStatus(index, status) {
        if (!statusList) return;
        
        const items = statusList.querySelectorAll('.status-item');
        const item = index === -1 ? items[items.length - 1] : items[index];
        
        if (item) {
            item.className = `status-item ${status}`;
            const icon = item.querySelector('.status-icon');
            if (icon) {
                icon.innerHTML = status === 'complete' ? '<i class="fas fa-check"></i>' : 
                                status === 'error' ? '<i class="fas fa-times"></i>' : 
                                '<i class="fas fa-spinner fa-spin"></i>';
            }
        }
    }
    
    function getLastStatus() {
        if (!statusList) return '';
        const items = statusList.querySelectorAll('.status-text');
        return items.length > 0 ? items[items.length - 1].textContent : '';
    }
    
    function updateProgress(percent, text) {
        if (progressBar) {
            progressBar.style.width = percent + '%';
            progressBar.textContent = Math.round(percent) + '%';
        }
        if (progressText) progressText.textContent = text;
    }
    
    function showResult(result) {
        if (progressSection) progressSection.classList.add('hidden');
        if (resultSection) resultSection.classList.remove('hidden');
        
        if (resultContent) {
            let html = '<div class="result-summary">';
            html += '<h4><i class="fas fa-chart-bar"></i> Processing Statistics</h4>';
            
            if (result.stats) {
                html += `<div class="stat-item"><span class="stat-label">Total Items:</span> <span class="stat-value">${result.stats.total || 0}</span></div>`;
                html += `<div class="stat-item"><span class="stat-label">Processed:</span> <span class="stat-value">${result.stats.processed || 0}</span></div>`;
                html += `<div class="stat-item"><span class="stat-label">Matched:</span> <span class="stat-value">${result.stats.matched || 0}</span></div>`;
                html += `<div class="stat-item"><span class="stat-label">Unmatched:</span> <span class="stat-value">${result.stats.unmatched || 0}</span></div>`;
                html += `<div class="stat-item"><span class="stat-label">Errors:</span> <span class="stat-value">${result.stats.errors || 0}</span></div>`;
            }
            
            html += `<div class="stat-item"><span class="stat-label">Processing Time:</span> <span class="stat-value">${result.processing_time || 'N/A'}</span></div>`;
            html += '</div>';
            
            if (result.download_url) {
                html += `<div class="download-section">
                    <a href="${result.download_url}" class="btn btn-success btn-lg">
                        <i class="fas fa-download"></i> Download Filled Excel
                    </a>
                </div>`;
            }
            
            if (result.summary_url) {
                html += `<a href="${result.summary_url}" class="btn btn-secondary" target="_blank">
                    <i class="fas fa-file-alt"></i> View Summary
                </a>`;
            }
            
            resultContent.innerHTML = html;
        }
        
        if (submitBtn) submitBtn.disabled = false;
    }
});
