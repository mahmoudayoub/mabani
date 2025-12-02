/**
 * Index Page JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('index-form');
    const jsonFiles = document.getElementById('json-files');
    const selectAll = document.getElementById('select-all');
    const selectedCount = document.getElementById('selected-count');
    const submitBtn = document.getElementById('submit-btn');
    const progressSection = document.getElementById('progress-section');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const resultSection = document.getElementById('result-section');
    const resultContent = document.getElementById('result-content');
    
    // Load available JSON files
    loadJsonFiles();
    
    async function loadJsonFiles() {
        try {
            const response = await fetch('/api/json-files');
            if (!response.ok) throw new Error('Failed to load JSON files');
            
            const data = await response.json();
            renderJsonFiles(data.files);
        } catch (error) {
            showError('Failed to load JSON files: ' + error.message);
        }
    }
    
    function renderJsonFiles(files) {
        if (!jsonFiles) return;
        
        if (files.length === 0) {
            jsonFiles.innerHTML = '<p class="no-files">No JSON files available. Please parse an Excel file first.</p>';
            if (submitBtn) submitBtn.disabled = true;
            return;
        }
        
        let html = '';
        files.forEach(file => {
            html += `
                <div class="file-item">
                    <label class="checkbox-label">
                        <input type="checkbox" name="files" value="${file.path}">
                        <span class="checkbox-custom"></span>
                        <span class="file-name">${file.name}</span>
                        <span class="file-size">${formatFileSize(file.size)}</span>
                        <span class="file-date">${formatDate(file.modified)}</span>
                    </label>
                </div>
            `;
        });
        jsonFiles.innerHTML = html;
        
        // Add change handlers
        jsonFiles.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', updateSelectedCount);
        });
    }
    
    // Select all handler
    if (selectAll) {
        selectAll.addEventListener('change', function() {
            const checkboxes = jsonFiles.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(cb => cb.checked = this.checked);
            updateSelectedCount();
        });
    }
    
    function updateSelectedCount() {
        const checked = jsonFiles.querySelectorAll('input[type="checkbox"]:checked').length;
        if (selectedCount) selectedCount.textContent = checked;
        if (submitBtn) submitBtn.disabled = checked === 0;
    }
    
    // Form submission
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(form);
            const selectedFiles = formData.getAll('files');
            
            if (selectedFiles.length === 0) {
                showError('Please select at least one JSON file');
                return;
            }
            
            // Show progress
            if (progressSection) progressSection.classList.remove('hidden');
            if (resultSection) resultSection.classList.add('hidden');
            if (submitBtn) submitBtn.disabled = true;
            
            try {
                updateProgress(10, 'Initializing indexer...');
                
                const response = await fetch('/api/index', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        files: selectedFiles,
                        namespace: formData.get('namespace'),
                        batch_size: parseInt(formData.get('batch_size')) || 100
                    })
                });
                
                updateProgress(30, 'Processing JSON files...');
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to index files');
                }
                
                // Poll for progress
                const taskId = (await response.json()).task_id;
                if (taskId) {
                    await pollProgress(taskId);
                } else {
                    const result = await response.json();
                    updateProgress(100, 'Complete!');
                    setTimeout(() => showResult(result), 500);
                }
                
            } catch (error) {
                showError(error.message);
                if (progressSection) progressSection.classList.add('hidden');
                if (submitBtn) submitBtn.disabled = false;
            }
        });
    }
    
    async function pollProgress(taskId) {
        while (true) {
            const response = await fetch(`/api/task/${taskId}`);
            const task = await response.json();
            
            if (task.status === 'completed') {
                updateProgress(100, 'Complete!');
                setTimeout(() => showResult(task.result), 500);
                break;
            } else if (task.status === 'failed') {
                throw new Error(task.error || 'Task failed');
            } else {
                updateProgress(task.progress || 50, task.message || 'Processing...');
            }
            
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
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
            html += `<div class="stat-item"><span class="stat-label">Vectors Indexed:</span> <span class="stat-value">${result.vectors_count || 0}</span></div>`;
            html += `<div class="stat-item"><span class="stat-label">Namespace:</span> <span class="stat-value">${result.namespace || 'default'}</span></div>`;
            html += `<div class="stat-item"><span class="stat-label">Processing Time:</span> <span class="stat-value">${result.processing_time || 'N/A'}</span></div>`;
            html += '</div>';
            
            if (result.message) {
                html += `<p class="result-message">${result.message}</p>`;
            }
            
            resultContent.innerHTML = html;
        }
        
        if (submitBtn) submitBtn.disabled = false;
    }
});
