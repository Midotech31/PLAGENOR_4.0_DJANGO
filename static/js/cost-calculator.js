/**
 * PLAGENOR 4.0 — Universal Cost Calculator
 * 
 * This module provides a future-proof, centralized cost estimation system
 * that works for ANY service without requiring code changes when new
 * services are added.
 * 
 * Features:
 * - Reads pricing configuration from data attributes (JSON)
 * - Auto-detects sample count from any form type (table rows, number inputs, etc.)
 * - Applies option_pricing multipliers (Duplicata ×2, Triplicata ×3)
 * - Applies field-level price modifiers (surcharges, discounts)
 * - Real-time updates on any form change
 * - Triggers Budget Guard via custom event
 * 
 * Formula: base_price × multiplier × sample_count + supplements
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        debug: true,  // Set to false in production
        currency: 'DA',
        locale: 'fr-FR',
    };

    // Debug logging
    function log(...args) {
        if (CONFIG.debug) {
            console.log('[CostCalculator]', ...args);
        }
    }

    function error(...args) {
        console.error('[CostCalculator]', ...args);
    }

    /**
     * Get pricing configuration from the DOM
     * Returns parsed pricing object or null if not found
     */
    function getPricingConfig() {
        // Try multiple possible sources
        const sources = [
            '#pricing-config',
            '#cost-estimate-box',
            '[data-pricing]',
        ];

        for (const selector of sources) {
            const el = document.querySelector(selector);
            if (!el) continue;

            // Try data-pricing-config attribute first (new format)
            const configAttr = el.getAttribute('data-pricing-config');
            if (configAttr) {
                try {
                    return JSON.parse(configAttr);
                } catch (e) {
                    error('Failed to parse data-pricing-config:', e);
                }
            }

            // Try data-pricing attribute (legacy format)
            const pricingAttr = el.getAttribute('data-pricing');
            if (pricingAttr && pricingAttr !== '{}') {
                try {
                    return JSON.parse(pricingAttr);
                } catch (e) {
                    error('Failed to parse data-pricing:', e);
                }
            }
        }

        log('No pricing configuration found');
        return null;
    }

    /**
     * Detect sample count from various form types
     * Handles:
     * - Dynamic tables (rows in #sample-table-body)
     * - Number inputs (name contains sample, echantillon, etc.)
     * - Text inputs with numeric values
     */
    function detectSampleCount() {
        let count = 0;
        let detectionMethod = 'none';

        // Method 1: Count rows in dynamic sample table
        const tableBody = document.getElementById('sample-table-body');
        if (tableBody) {
            const rows = tableBody.querySelectorAll('tr');
            // Filter out empty rows (rows with no filled inputs)
            const nonEmptyRows = Array.from(rows).filter(row => {
                const inputs = row.querySelectorAll('input, select');
                return Array.from(inputs).some(input => {
                    if (input.type === 'hidden') return false;
                    if (input.type === 'checkbox') return input.checked;
                    return input.value && input.value.trim() !== '';
                });
            });
            
            if (nonEmptyRows.length > 0) {
                count = nonEmptyRows.length;
                detectionMethod = 'table_rows_nonempty';
            } else if (rows.length > 0) {
                // Fall back to total rows if none have data yet
                count = rows.length;
                detectionMethod = 'table_rows_total';
            }
        }

        // Method 2: Look for explicit sample count input
        if (count === 0) {
            const sampleInputSelectors = [
                'input[name*="sample_count"]',
                'input[name*="nombre_echantillons"]',
                'input[name*="nb_echantillons"]',
                'input[name*="nb_samples"]',
                'input[name*="number_of_samples"]',
                'input[name*="sample_count"]',
                'input[name*="samples"]',
                'input[name*="echantillons"]',
            ];

            for (const selector of sampleInputSelectors) {
                const input = document.querySelector(selector);
                if (input) {
                    const value = parseInt(input.value, 10);
                    if (!isNaN(value) && value > 0) {
                        count = value;
                        detectionMethod = `input_${selector}`;
                        break;
                    }
                }
            }
        }

        // Method 3: Count sample_ prefixed inputs (for forms without tables)
        if (count === 0) {
            const sampleInputs = document.querySelectorAll('input[name^="sample_"]');
            if (sampleInputs.length > 0) {
                // Group by row index (sample_0_col, sample_1_col, etc.)
                const rowIndices = new Set();
                sampleInputs.forEach(input => {
                    const match = input.name.match(/sample_(\d+)_/);
                    if (match) {
                        rowIndices.add(match[1]);
                    }
                });
                if (rowIndices.size > 0) {
                    count = rowIndices.size;
                    detectionMethod = 'sample_inputs';
                }
            }
        }

        // Default to 1 if no samples detected but form exists
        if (count === 0 && document.getElementById('dynamic-service-form')) {
            const formContent = document.getElementById('dynamic-service-form').innerHTML;
            if (formContent.includes('sample') || formContent.includes('échantillon')) {
                count = 1;  // Assume at least 1 sample
                detectionMethod = 'default_assumed';
            }
        }

        log(`Sample count detected: ${count} (method: ${detectionMethod})`);
        return { count, detectionMethod };
    }

    /**
     * Extract base price from pricing configuration
     */
    function getBasePrice(pricing) {
        if (!pricing) return 0;

        // New format: configs array from ServicePricing
        if (pricing.configs && Array.isArray(pricing.configs)) {
            // Find BASE or PER_SAMPLE config
            for (const cfg of pricing.configs) {
                if (cfg.pricing_type === 'BASE' || cfg.pricing_type === 'PER_SAMPLE') {
                    log('Base price from configs:', cfg.amount);
                    return cfg.amount || 0;
                }
            }
        }

        // Legacy format: base_price field
        if (pricing.base_price) {
            if (typeof pricing.base_price === 'number') {
                return pricing.base_price;
            }
            if (typeof pricing.base_price === 'object') {
                // Return non_pathogenic price by default
                return pricing.base_price.non_pathogenic || 
                       pricing.base_price.default || 
                       pricing.base_price.pathogenic || 0;
            }
        }

        // Fallback to service's legacy price field
        const fallbackEl = document.querySelector('[data-service-price]');
        if (fallbackEl) {
            return parseFloat(fallbackEl.getAttribute('data-service-price')) || 0;
        }

        return 0;
    }

    /**
     * Extract option pricing multipliers from form fields
     * Returns array of multipliers to apply (e.g., [2, 3] for Duplicata + Triplicata)
     */
    function getOptionMultipliers() {
        const multipliers = [];
        const appliedOptions = [];

        // Find all fields with option_pricing data
        document.querySelectorAll('[data-option-pricing]').forEach(fieldGroup => {
            const optionPricingAttr = fieldGroup.getAttribute('data-option-pricing');
            if (!optionPricingAttr) return;

            let optionPricing;
            try {
                optionPricing = JSON.parse(optionPricingAttr);
            } catch (e) {
                return;
            }

            if (!optionPricing || typeof optionPricing !== 'object') return;

            // Find the input/select in this field group
            const input = fieldGroup.querySelector('select, input[type="checkbox"]');
            if (!input) return;

            // Skip if field is hidden
            if (fieldGroup.style.display === 'none' || fieldGroup.offsetParent === null) {
                return;
            }

            let selectedValue = null;

            if (input.tagName === 'SELECT') {
                selectedValue = input.value;
            } else if (input.type === 'checkbox') {
                selectedValue = input.checked ? input.value : null;
            }

            if (!selectedValue) return;

            // Check if selected value has a multiplier
            if (optionPricing[selectedValue] !== undefined) {
                const multiplier = parseFloat(optionPricing[selectedValue]);
                if (!isNaN(multiplier) && multiplier > 0) {
                    multipliers.push(multiplier);
                    appliedOptions.push({
                        field: fieldGroup.getAttribute('data-pricing-field') || 'unknown',
                        option: selectedValue,
                        multiplier: multiplier
                    });
                }
            }
        });

        // Also check for data-option-price on selected options (legacy)
        document.querySelectorAll('select option:checked[data-option-price]').forEach(option => {
            const price = parseFloat(option.getAttribute('data-option-price'));
            if (!isNaN(price) && price > 0 && !multipliers.includes(price)) {
                multipliers.push(price);
                appliedOptions.push({
                    source: 'legacy_option_attribute',
                    multiplier: price
                });
            }
        });

        if (appliedOptions.length > 0) {
            log('Applied multipliers:', appliedOptions);
        }

        return multipliers;
    }

    /**
     * Get surcharges from field-level price modifiers
     */
    function getSurcharges() {
        const surcharges = [];

        document.querySelectorAll('[data-pricing-field]').forEach(fieldGroup => {
            // Skip hidden fields
            if (fieldGroup.style.display === 'none' || fieldGroup.offsetParent === null) return;

            const pricingType = fieldGroup.getAttribute('data-pricing-type');
            const pricingValue = parseFloat(fieldGroup.getAttribute('data-pricing-value')) || 0;

            if (!pricingType || pricingValue === 0) return;

            const input = fieldGroup.querySelector('input, select');
            if (!input) return;

            let isActive = false;

            if (input.type === 'checkbox') {
                isActive = input.checked;
            } else if (input.tagName === 'SELECT') {
                isActive = input.value !== '';
            } else {
                isActive = input.value && input.value.trim() !== '';
            }

            if (isActive && pricingType === 'add') {
                surcharges.push({
                    type: 'add',
                    amount: pricingValue,
                    field: fieldGroup.getAttribute('data-pricing-field')
                });
            }
        });

        return surcharges;
    }

    /**
     * Calculate total cost
     * Formula: base_price × multiplier × sample_count + supplements
     */
    function calculateCost() {
        const pricing = getPricingConfig();
        if (!pricing) {
            log('No pricing config available');
            return null;
        }

        const basePrice = getBasePrice(pricing);
        if (basePrice === 0) {
            log('Base price is 0, skipping calculation');
            return null;
        }

        const { count: sampleCount } = detectSampleCount();
        const multipliers = getOptionMultipliers();
        const surcharges = getSurcharges();

        // Start with base price per sample
        let total = basePrice * sampleCount;
        const breakdown = {
            basePrice,
            sampleCount,
            baseTotal: total,
            multipliers: [],
            surcharges: [],
            finalTotal: total
        };

        // Apply multipliers (e.g., Duplicata ×2)
        multipliers.forEach(mult => {
            total *= mult;
            breakdown.multipliers.push(mult);
        });

        breakdown.afterMultipliers = total;

        // Apply surcharges (per sample)
        surcharges.forEach(surcharge => {
            const amount = surcharge.amount * sampleCount;
            total += amount;
            breakdown.surcharges.push({
                ...surcharge,
                totalAmount: amount
            });
        });

        breakdown.finalTotal = total;

        log('Cost calculation:', breakdown);

        return {
            total,
            breakdown,
            formatted: formatCurrency(total)
        };
    }

    /**
     * Format number as currency
     */
    function formatCurrency(amount) {
        return amount.toLocaleString(CONFIG.locale) + ' ' + CONFIG.currency;
    }

    /**
     * Update the cost estimate display
     */
    function updateCostEstimate() {
        const costEl = document.getElementById('cost-estimate');
        if (!costEl) {
            error('Cost estimate element (#cost-estimate) not found');
            return;
        }

        const result = calculateCost();

        if (result === null) {
            // No pricing available, keep the dash
            costEl.textContent = '—';
            log('Cost calculation returned null');
        } else {
            costEl.textContent = result.formatted;
            log('Updated cost estimate:', result.formatted);
        }

        // Trigger budget update event for Budget Guard
        document.dispatchEvent(new CustomEvent('costUpdated', {
            detail: result || { total: 0 }
        }));

        // Update summary if present
        updateSummary(result);
    }

    /**
     * Update the pricing modifiers summary display
     */
    function updateSummary(result) {
        const summaryEl = document.getElementById('pricing-modifiers-summary');
        const listEl = document.getElementById('active-modifiers-list');

        if (!summaryEl || !listEl) return;

        if (!result || !result.breakdown) {
            summaryEl.style.display = 'none';
            return;
        }

        const { breakdown } = result;
        const items = [];

        // Add multiplier info
        if (breakdown.multipliers.length > 0) {
            breakdown.multipliers.forEach(mult => {
                items.push(`×${mult} (multiplicateur)`);
            });
        }

        // Add surcharge info
        if (breakdown.surcharges.length > 0) {
            breakdown.surcharges.forEach(surcharge => {
                items.push(`+${surcharge.totalAmount.toLocaleString(CONFIG.locale)} DA (${surcharge.field})`);
            });
        }

        if (items.length > 0) {
            summaryEl.style.display = 'block';
            listEl.innerHTML = items.map(item => 
                `<div style="color:#059669;">${item}</div>`
            ).join('');
        } else {
            summaryEl.style.display = 'none';
        }
    }

    /**
     * Initialize event listeners
     */
    function initEventListeners() {
        log('Initializing event listeners');

        // Listen for changes on all parameter fields
        document.addEventListener('change', function(e) {
            if (e.target.name && (
                e.target.name.startsWith('param_') ||
                e.target.name.startsWith('sample_')
            )) {
                log('Change detected on:', e.target.name);
                updateCostEstimate();
            }
        });

        // Listen for input changes (for number inputs)
        document.addEventListener('input', function(e) {
            if (e.target.type === 'number' && e.target.name) {
                if (e.target.name.includes('sample') || e.target.name.includes('echantillon')) {
                    log('Sample count input changed:', e.target.name, e.target.value);
                    updateCostEstimate();
                }
            }
        });

        // Listen for sample row events
        document.addEventListener('sampleRowAdded', function() {
            log('Sample row added');
            updateCostEstimate();
        });

        document.addEventListener('sampleRowDeleted', function() {
            log('Sample row deleted');
            updateCostEstimate();
        });

        // Listen for cost update requests
        document.addEventListener('costUpdateRequested', function() {
            log('Cost update requested');
            updateCostEstimate();
        });

        // Listen for form loaded event (from AJAX)
        document.addEventListener('serviceFormLoaded', function() {
            log('Service form loaded');
            // Small delay to ensure DOM is ready
            setTimeout(updateCostEstimate, 100);
        });
    }

    /**
     * Initialize on DOM ready
     */
    function init() {
        log('Initializing Cost Calculator');
        initEventListeners();
        
        // Initial calculation if form is already present
        if (document.getElementById('cost-estimate-box')) {
            setTimeout(updateCostEstimate, 200);
        }
    }

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        // DOM already loaded
        init();
    }

    // Expose public API
    window.PlagenorCostCalculator = {
        calculateCost,
        updateCostEstimate,
        getPricingConfig,
        detectSampleCount,
        formatCurrency,
        CONFIG
    };

    log('Module loaded');
})();
