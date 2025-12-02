# ===== Theme Configuration =====
# Balanced dark theme for WebCamShare (eye-friendly with good contrast)

class Theme:
    # Colors - Balanced Dark Palette
    BG_DARK = "#1a1a20"           # Dark but not pure black
    BG_CARD = "#24242c"           # Card/Frame background
    BG_INPUT = "#2e2e38"          # Input field background
    BG_PREVIEW = "#1e1e24"        # Preview area background
    
    ACCENT = "#4db8a6"            # Balanced teal (visible but not harsh)
    ACCENT_HOVER = "#3da898"      # Accent hover state
    ACCENT_DANGER = "#e57373"     # Balanced red
    ACCENT_DANGER_HOVER = "#d46363"
    
    TEXT_PRIMARY = "#f0f0f4"      # Bright but not pure white
    TEXT_SECONDARY = "#a0a0b0"    # Clear secondary text
    TEXT_ACCENT = "#5cc8b8"       # Visible accent text
    
    # Status colors (clear but not harsh)
    STATUS_SUCCESS = "#5cc8b8"
    STATUS_WARNING = "#e0c050"    # Clear yellow
    STATUS_ERROR = "#e57373"
    STATUS_IDLE = "#888898"
    
    # Typography
    FONT_FAMILY = "Segoe UI"
    FONT_TITLE = (FONT_FAMILY, 28, "bold")
    FONT_HEADING = (FONT_FAMILY, 18, "bold")
    FONT_BODY = (FONT_FAMILY, 13)
    FONT_SMALL = (FONT_FAMILY, 11)
    FONT_BUTTON = (FONT_FAMILY, 14, "bold")
    
    # Spacing
    PAD_XS = 4
    PAD_SM = 8
    PAD_MD = 16
    PAD_LG = 24
    PAD_XL = 40
    
    # Radius
    RADIUS_SM = 8
    RADIUS_MD = 12
    RADIUS_LG = 16
