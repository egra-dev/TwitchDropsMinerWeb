/**
 * campaign-filters.js - Handles campaign filtering functionality
 * Adds a dropdown filter for campaign visibility modes.
 */

// Use global variable set in global-exports.js
if (typeof window.originalCampaignsData === 'undefined') {
    window.originalCampaignsData = [];
}

// Initialize campaign filters
function initCampaignFilters() {
    const campaignFilter = document.getElementById('campaign-filter');
    if (!campaignFilter) return;
    
    campaignFilter.addEventListener('change', applyCampaignFilters);
    
    // Add refresh button event listener
    const refreshCampaignsButton = document.getElementById('refresh-campaigns');
    if (refreshCampaignsButton) {
        refreshCampaignsButton.addEventListener('click', () => {
            // Visual feedback for refresh
            const originalText = refreshCampaignsButton.innerHTML;
            refreshCampaignsButton.disabled = true;
            refreshCampaignsButton.innerHTML = '<i class="fas fa-sync fa-spin mr-1"></i> Refreshing...';
            
            // Save scroll position before refreshing
            if (window.saveCurrentScrollPosition) {
                window.saveCurrentScrollPosition();
            }            // Refresh campaigns data
            if (typeof window.fetchCampaigns !== 'function') {
                window.showToast('Error', 'Refresh functionality not available', 'error');
                refreshCampaignsButton.disabled = false;
                refreshCampaignsButton.innerHTML = originalText;
                return;
            }
            
            window.fetchCampaigns()
                .then(data => {
                    window.originalCampaignsData = [...data]; // Keep original data for filtering
                    applyCampaignFilters(); // Apply filters to the new data
                })                .catch(error => {
                    if (typeof window.showToast === 'function') {
                        window.showToast('Error', 'Failed to refresh campaigns', 'error');
                    }
                })
                .finally(() => {
                    // Reset the button
                    setTimeout(() => {
                        refreshCampaignsButton.disabled = false;
                        refreshCampaignsButton.innerHTML = originalText;
                    }, 500);
                });
        });
    }    
    // Campaign Filters initialized
}

// Apply the selected campaign filter.
function applyCampaignFilters() {
    const campaignFilter = document.getElementById('campaign-filter');
    if (!campaignFilter || !Array.isArray(window.originalCampaignsData)) return;
    const selectedFilter = campaignFilter.value;
    let filteredData = [...window.originalCampaignsData];
    
    if (selectedFilter !== 'all') {
        filteredData = filteredData.filter(campaign => {
            switch (selectedFilter) {
                case 'not-linked':
                    return !(campaign.linked || campaign.eligible);
                case 'upcoming':
                    return campaign.upcoming === true || isCampaignNotPassed(campaign);
                case 'excluded':
                    return campaign.excluded;
                case 'finished':
                    return campaign.finished;
                default:
                    return true;
            }
        });
    }
    
    // Update campaigns UI with filtered data
    if (typeof window.updateCampaignsUI === 'function') {
        window.updateCampaignsUI(filteredData);
    } 
    // If function not available, silently fail
}

function isCampaignNotPassed(campaign) {
    if (!campaign) return false;
    if (campaign.upcoming === true) return true;
    if (!campaign.end_time) return false;

    const endTime = Date.parse(campaign.end_time);
    return !Number.isNaN(endTime) && endTime > Date.now();
}

// Override the global placeholder function
window.applyCampaignFilters = applyCampaignFilters;

// Add listener for tab changes to apply filters when switching to campaigns tab
function addTabChangeListener() {
    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabId = button.id.replace('tab-btn-', '');
            if (tabId === 'campaigns' && typeof applyCampaignFilters === 'function') {
                // Small delay to ensure tab is fully visible
                setTimeout(() => {
                    applyCampaignFilters();
                }, 100);
            }
        });
    });
}

// Init on page load
document.addEventListener('DOMContentLoaded', () => {
    // Increased delay to ensure main.js has fully loaded and all functions are defined
    setTimeout(() => {
        initCampaignFilters();
        addTabChangeListener();
        applyCampaignFilters();
    }, 300);
});
