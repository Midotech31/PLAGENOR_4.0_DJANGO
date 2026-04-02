"""
Unified position choices for PLAGENOR 4.0
Channel-specific choices combined into one file
"""
from django.utils.translation import gettext_lazy as _

# IBTIKAR Position Choices (for students/researchers)
IBTIKAR_POSITION_CHOICES = [
    ('doctorant', _('Doctorant(e) / PhD Student')),
    ('etudiant_licence', _('Étudiant(e) en fin de cycle — Licence')),
    ('etudiant_master_ingenieur', _('Étudiant(e) en fin de cycle — Master / Ingénieur')),
]

# GENOCLAB Position Choices (for external clients - professional roles)
GENOCLAB_POSITION_CHOICES = [
    ('director', _('Directeur / Director')),
    ('manager', _('Responsable / Manager')),
    ('lab_technician', _('Technicien de laboratoire / Lab Technician')),
    ('researcher', _('Chercheur / Researcher')),
    ('engineer', _('Ingénieur / Engineer')),
    ('other', _('Autre / Other')),
]

# Member Position Choices (for analysts/operators - admin-created only)
MEMBER_POSITION_CHOICES = [
    ('chercheur', _('Chercheur')),
    ('mca', _('MCA')),
    ('mcb', _('MCB')),
    ('professeur', _('Professeur')),
    ('ingenieur', _('Ingénieur')),
    ('technicien', _('Technicien')),
    ('doctorant', _('Doctorant(e)')),
]

# Combined choices for model field (accepts all values)
ALL_POSITION_CHOICES = IBTIKAR_POSITION_CHOICES + GENOCLAB_POSITION_CHOICES + MEMBER_POSITION_CHOICES


def get_position_display(position_key, channel=None):
    """
    Get display label for a position key based on channel context.
    
    Args:
        position_key: The database key for the position
        channel: 'IBTIKAR', 'GENOCLAB', 'MEMBER', or None for auto-detect
    
    Returns:
        Translated display string or the key if not found
    """
    if not position_key:
        return ''
    
    # Create lookup dictionaries
    ibtikar_dict = dict(IBTIKAR_POSITION_CHOICES)
    genoclab_dict = dict(GENOCLAB_POSITION_CHOICES)
    member_dict = dict(MEMBER_POSITION_CHOICES)
    all_dict = dict(ALL_POSITION_CHOICES)
    
    # If channel specified, use that lookup first
    if channel == 'IBTIKAR' and position_key in ibtikar_dict:
        return ibtikar_dict[position_key]
    elif channel == 'GENOCLAB' and position_key in genoclab_dict:
        return genoclab_dict[position_key]
    elif channel == 'MEMBER' and position_key in member_dict:
        return member_dict[position_key]
    
    # Fallback to combined lookup
    return all_dict.get(position_key, position_key)


def get_position_choices_for_channel(channel):
    """
    Get position choices filtered by channel.
    
    Args:
        channel: 'IBTIKAR', 'GENOCLAB', or 'MEMBER'
    
    Returns:
        List of (key, label) tuples
    """
    if channel == 'IBTIKAR':
        return [('', _('— Sélectionner —'))] + IBTIKAR_POSITION_CHOICES
    elif channel == 'GENOCLAB':
        return [('', _('— Sélectionner —'))] + GENOCLAB_POSITION_CHOICES
    elif channel == 'MEMBER':
        return [('', _('— Sélectionner —'))] + MEMBER_POSITION_CHOICES
    else:
        return [('', _('— Sélectionner —'))] + ALL_POSITION_CHOICES
