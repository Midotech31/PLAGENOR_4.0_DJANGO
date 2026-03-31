from django import template

register = template.Library()

# SVG Icons dictionary
ICONS = {
    'analysis': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M9 3v18"/><path d="M15 3v18"/><path d="M3 9h18"/><path d="M3 15h18"/></svg>',
    
    'flask': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M10 2v7.31"/><path d="M14 2v7.31"/><path d="M8.5 2h7"/><path d="M14 9.3a6.5 6.5 0 1 1-4 0"/></svg>',
    
    'payment': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01"/><path d="M2 10h20"/></svg>',
    
    'money': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><circle cx="12" cy="12" r="10"/><path d="M12 6v12"/><path d="M8 10h8"/><path d="M8 14h8"/></svg>',
    
    'report': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>',
    
    'file': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    
    'appointment': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    
    'calendar': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    
    'assigned': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    
    'user': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    
    'quote': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
    
    'check': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><polyline points="20 6 9 17 4 12"/></svg>',
    
    'validated': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    
    'rejected': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    
    'warning': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    
    'mail': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
    
    'notification': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
    
    'info': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    
    'gift': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><polyline points="20 12 20 22 4 22 4 12"/><rect x="2" y="7" width="20" height="5"/><line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/></svg>',
    
    'sample': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M10 2h4"/><path d="M12 2v8"/><path d="M12 10v12"/><path d="M8 22h8"/></svg>',
    
    'dna': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px; height:20px;"><path d="M12 2v20"/><path d="M8 6c0 4 4 4 4 8s-4 4-4 8"/><path d="M16 6c0 4-4 4-4 8s4 4 4 8"/></svg>',
}

# Keyword to icon mapping
KEYWORD_MAP = {
    'analyse': 'flask',
    'analysis': 'flask',
    'rapport': 'report',
    'report': 'report',
    'paiement': 'money',
    'payment': 'money',
    'payé': 'money',
    'devis': 'quote',
    'quote': 'quote',
    'rdv': 'appointment',
    'rendez-vous': 'appointment',
    'appointment': 'appointment',
    'assigné': 'assigned',
    'assigned': 'assigned',
    'attribué': 'assigned',
    'validé': 'validated',
    'validée': 'validated',
    'validated': 'validated',
    'rejeté': 'rejected',
    'rejetée': 'rejected',
    'rejected': 'rejected',
    'refusé': 'rejected',
    'refused': 'rejected',
    'échantillon': 'sample',
    'sample': 'sample',
    'colis': 'sample',
    'cadeau': 'gift',
    'gift': 'gift',
    'notification': 'notification',
    'email': 'mail',
    'message': 'mail',
    'facture': 'payment',
    'invoice': 'payment',
    'terminé': 'check',
    'completed': 'check',
    'complété': 'check',
    'clôturé': 'check',
    'closed': 'check',
}

@register.filter
def notification_icon(message):
    """Return appropriate icon SVG based on notification message content."""
    if not message:
        return ICONS['info']
    
    message_lower = message.lower()
    
    # Check for keywords in message
    for keyword, icon_name in KEYWORD_MAP.items():
        if keyword in message_lower:
            return ICONS.get(icon_name, ICONS['info'])
    
    # Default icon
    return ICONS['notification']


@register.filter
def notification_icon_color(message):
    """Return appropriate color based on notification message content."""
    if not message:
        return '#64748b'  # slate-500
    
    message_lower = message.lower()
    
    # Error/Rejected - Red
    if any(word in message_lower for word in ['rejeté', 'rejetée', 'rejected', 'refusé', 'refused', 'erreur', 'error']):
        return '#dc2626'  # red-600
    
    # Success/Validated - Green
    if any(word in message_lower for word in ['validé', 'validée', 'validated', 'confirmé', 'confirmed', 'terminé', 'completed', 'complété', 'accepté', 'accepted']):
        return '#16a34a'  # green-600
    
    # Payment/Money - Amber/Gold
    if any(word in message_lower for word in ['paiement', 'payment', 'payé', 'devis', 'quote', 'facture', 'invoice']):
        return '#d97706'  # amber-600
    
    # Analysis/Report - Blue
    if any(word in message_lower for word in ['analyse', 'analysis', 'rapport', 'report', 'échantillon', 'sample']):
        return '#2563eb'  # blue-600
    
    # Warning - Orange
    if any(word in message_lower for word in ['warning', 'attention', 'alerte', 'alert']):
        return '#ea580c'  # orange-600
    
    # Default - Slate
    return '#64748b'  # slate-500
