/**
 * Query Page JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('query-form');
    const queryInput = document.getElementById('query-input');
    const submitBtn = document.getElementById('submit-btn');
    const resultsSection = document.getElementById('results-section');
    const resultsContainer = document.getElementById('results-container');
    const resultCount = document.getElementById('result-count');
    const queryTime = document.getElementById('query-time');
    
    // Form submission
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const query = queryInput.value.trim();
            if (!query) {
                showError('Please enter a search query');
                return;
            }
            
            const formData = new FormData(form);
            
            showLoading('Searching...');
            if (submitBtn) submitBtn.disabled = true;
            
            try {
                const startTime = Date.now();
                
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        query: query,
                        namespace: formData.get('namespace') || '',
                        top_k: parseInt(formData.get('top_k')) || 10,
                        threshold: parseFloat(formData.get('threshold')) || 0.0
                    })
                });
                
                hideLoading();
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Query failed');
                }
                
                const result = await response.json();
                const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
                
                showResults(result, elapsed);
                
            } catch (error) {
                hideLoading();
                showError(error.message);
            } finally {
                if (submitBtn) submitBtn.disabled = false;
            }
        });
    }
    
    // Real-time search (debounced)
    if (queryInput) {
        queryInput.addEventListener('input', debounce(function() {
            // Could implement real-time suggestions here
        }, 300));
    }
    
    function showResults(result, elapsed) {
        if (resultsSection) resultsSection.classList.remove('hidden');
        if (resultCount) resultCount.textContent = result.results?.length || 0;
        if (queryTime) queryTime.textContent = elapsed + 's';
        
        if (resultsContainer) {
            if (!result.results || result.results.length === 0) {
                resultsContainer.innerHTML = `
                    <div class="no-results">
                        <i class="fas fa-search"></i>
                        <p>No results found</p>
                        <small>Try a different search query or adjust the filters</small>
                    </div>
                `;
                return;
            }
            
            let html = '';
            result.results.forEach((item, index) => {
                const score = (item.score * 100).toFixed(1);
                const scoreClass = score >= 80 ? 'high' : score >= 60 ? 'medium' : 'low';
                
                html += `
                    <div class="result-item">
                        <div class="result-header">
                            <span class="result-rank">#${index + 1}</span>
                            <span class="result-score ${scoreClass}">${score}%</span>
                        </div>
                        <div class="result-content">
                            <h4 class="result-title">${escapeHtml(item.description || 'No description')}</h4>
                            <div class="result-meta">
                                ${item.rate ? `<span class="meta-item"><i class="fas fa-tag"></i> ${escapeHtml(item.rate)}</span>` : ''}
                                ${item.unit ? `<span class="meta-item"><i class="fas fa-ruler"></i> ${escapeHtml(item.unit)}</span>` : ''}
                                ${item.category ? `<span class="meta-item"><i class="fas fa-folder"></i> ${escapeHtml(item.category)}</span>` : ''}
                            </div>
                            ${item.hierarchy ? `
                                <div class="result-hierarchy">
                                    <small><i class="fas fa-sitemap"></i> ${escapeHtml(item.hierarchy)}</small>
                                </div>
                            ` : ''}
                        </div>
                        <div class="result-actions">
                            <button class="btn btn-sm btn-secondary" onclick="copyToClipboard('${escapeHtml(item.rate || '')}')">
                                <i class="fas fa-copy"></i> Copy Rate
                            </button>
                        </div>
                    </div>
                `;
            });
            
            resultsContainer.innerHTML = html;
        }
    }
    
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});

// Copy to clipboard helper
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showSuccess('Copied to clipboard!');
    }).catch(err => {
        showError('Failed to copy: ' + err.message);
    });
}
