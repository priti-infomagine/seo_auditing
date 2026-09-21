"""add_url_ignore_patterns_table

Revision ID: abc123
Revises: 0446c765815e
Create Date: 2026-09-21 12:05:44.767941

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'abc123'
down_revision: Union[str, Sequence[str], None] = '0446c765815e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create url_ignore_patterns table
    op.create_table(
        'url_ignore_patterns',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('record_type', sa.Text(), nullable=False),
        sa.Column('scope', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('match_type', sa.Text(), nullable=True),
        sa.Column('pattern', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('audit_id', UUID(as_uuid=True), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('normalized_url', sa.Text(), nullable=True),
        sa.Column('matched_pattern_id', UUID(as_uuid=True), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    
    # Add check constraints
    op.create_check_constraint(
        'chk_record_type',
        'url_ignore_patterns',
        "record_type IN ('pattern', 'skip')"
    )
    op.create_check_constraint(
        'chk_scope',
        'url_ignore_patterns',
        "scope IN ('global', 'performance', 'accessibility', 'bestpractices', 'seo', 'runtime')"
    )
    op.create_check_constraint(
        'chk_match_type',
        'url_ignore_patterns',
        "match_type IN ('path', 'prefix', 'extension', 'query_param', 'regex', 'scheme', 'host') OR match_type IS NULL"
    )
    op.create_check_constraint(
        'chk_pattern_fields',
        'url_ignore_patterns',
        "(record_type = 'pattern' AND ((match_type IS NOT NULL AND pattern IS NOT NULL) OR scope IN ('performance', 'accessibility', 'bestpractices', 'seo'))) OR (record_type = 'skip' AND audit_id IS NOT NULL AND url IS NOT NULL)"
    )
    
    # Add foreign key constraints
    op.create_foreign_key(
        'fk_url_ignore_patterns_audit_id',
        'url_ignore_patterns', 'crawl_jobs',
        ['audit_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_url_ignore_patterns_matched_pattern_id',
        'url_ignore_patterns', 'url_ignore_patterns',
        ['matched_pattern_id'], ['id']
    )
    
    # Create indexes
    op.create_index(
        'ix_url_ignore_patterns_lookup',
        'url_ignore_patterns',
        ['scope', 'is_active', 'sort_order'],
        postgresql_where=sa.text("record_type = 'pattern' AND is_active = TRUE")
    )
    op.create_index(
        'ix_url_ignore_patterns_skips_audit',
        'url_ignore_patterns',
        ['audit_id'],
        postgresql_where=sa.text("record_type = 'skip'")
    )
    op.create_index(
        'ix_url_ignore_patterns_skips_reason',
        'url_ignore_patterns',
        ['audit_id', 'reason'],
        postgresql_where=sa.text("record_type = 'skip'")
    )
    op.create_index(
        'ix_url_ignore_patterns_skips_matched',
        'url_ignore_patterns',
        ['matched_pattern_id'],
        postgresql_where=sa.text("record_type = 'skip'")
    )
    op.create_index(
        'ix_url_ignore_patterns_unique',
        'url_ignore_patterns',
        ['scope', 'match_type', 'pattern'],
        unique=True,
        postgresql_where=sa.text("record_type = 'pattern'")
    )
    
    # 2. Add pages_skipped column to crawl_jobs
    op.add_column(
        'crawl_jobs',
        sa.Column('pages_skipped', sa.Integer(), nullable=False, server_default=sa.text('0'))
    )
    
    # 3. Insert seed data (pattern definitions)
    _insert_seed_data()


def _insert_seed_data() -> None:
    """Insert all seed patterns as record_type='pattern' rows."""
    connection = op.get_bind()
    
    # Helper to insert a pattern
    def insert_pattern(scope, match_type, pattern, reason, description, sort_order=0):
        connection.execute(
            sa.text("""
                INSERT INTO url_ignore_patterns 
                (record_type, scope, match_type, pattern, reason, description, is_active, is_default, sort_order)
                VALUES ('pattern', :scope, :match_type, :pattern, :reason, :description, TRUE, TRUE, :sort_order)
            """),
            {
                'scope': scope,
                'match_type': match_type,
                'pattern': pattern,
                'reason': reason,
                'description': description,
                'sort_order': sort_order
            }
        )
    
    # ===== GLOBAL PATTERNS =====
    # Tracking parameters
    insert_pattern('global', 'query_param', 'utm_', 'tracking_params', 'UTM tracking parameters', 10)
    insert_pattern('global', 'query_param', 'gclid', 'tracking_params', 'Google click identifier', 11)
    insert_pattern('global', 'query_param', 'fbclid', 'tracking_params', 'Facebook click identifier', 12)
    insert_pattern('global', 'query_param', 'msclkid', 'tracking_params', 'Microsoft click identifier', 13)
    
    # Session parameters
    insert_pattern('global', 'query_param', 'sessionid', 'session_params', 'Session identifiers', 20)
    insert_pattern('global', 'query_param', 'sid', 'session_params', 'Session identifiers', 21)
    insert_pattern('global', 'query_param', 'token', 'session_params', 'Authentication tokens', 22)
    insert_pattern('global', 'query_param', 'ref', 'session_params', 'Referral parameters', 23)
    
    # Faceted parameters
    insert_pattern('global', 'query_param', 'source', 'faceted_params', 'Source parameters (faceted)', 30)
    insert_pattern('global', 'query_param', 'sort', 'faceted_params', 'Sort parameters (crawl trap)', 31)
    insert_pattern('global', 'query_param', 'filter', 'faceted_params', 'Filter parameters (crawl trap)', 32)
    insert_pattern('global', 'query_param', 'order', 'faceted_params', 'Order parameters (crawl trap)', 33)
    insert_pattern('global', 'query_param', 'view', 'faceted_params', 'View parameters (crawl trap)', 34)
    insert_pattern('global', 'query_param', 'display', 'faceted_params', 'Display parameters (crawl trap)', 35)
    
    # Search parameters
    insert_pattern('global', 'query_param', 'q', 'search_params', 'Search query parameter', 40)
    insert_pattern('global', 'query_param', 's', 'search_params', 'Search query parameter', 41)
    
    # Admin/System paths
    insert_pattern('global', 'prefix', '/wp-admin/', 'admin_path', 'WordPress admin paths', 50)
    insert_pattern('global', 'path', '/wp-login.php', 'admin_path', 'WordPress login page', 51)
    insert_pattern('global', 'prefix', '/wp-json/', 'admin_path', 'WordPress REST API', 52)
    insert_pattern('global', 'prefix', '/wp-content/', 'admin_path', 'WordPress content directory', 53)
    insert_pattern('global', 'prefix', '/wp-includes/', 'admin_path', 'WordPress includes', 54)
    insert_pattern('global', 'path', '/admin', 'admin_path', 'Admin panel root', 55)
    insert_pattern('global', 'path', '/administrator', 'admin_path', 'Joomla admin panel', 56)
    insert_pattern('global', 'path', '/cpanel', 'admin_path', 'Control panel', 57)
    insert_pattern('global', 'path', '/phpmyadmin', 'admin_path', 'phpMyAdmin', 58)
    
    # API paths
    insert_pattern('global', 'prefix', '/api/', 'api_path', 'API endpoints', 60)
    insert_pattern('global', 'path', '/graphql', 'api_path', 'GraphQL endpoint', 61)
    insert_pattern('global', 'path', '/xmlrpc.php', 'api_path', 'XML-RPC endpoint', 62)
    insert_pattern('global', 'prefix', '/cgi-bin/', 'api_path', 'CGI scripts', 63)
    
    # System paths
    insert_pattern('global', 'prefix', '/cdn-cgi/', 'system_path', 'Cloudflare internal paths', 70)
    insert_pattern('global', 'prefix', '/.well-known/', 'system_path', 'Well-known URIs (RFC 5785)', 71)
    insert_pattern('global', 'prefix', '/.git/', 'system_path', 'Git repository', 72)
    insert_pattern('global', 'path', '/.env', 'system_path', 'Environment file', 73)
    
    # Auth paths
    insert_pattern('global', 'path', '/login', 'auth_path', 'Login page', 80)
    insert_pattern('global', 'path', '/signin', 'auth_path', 'Sign in page', 81)
    insert_pattern('global', 'path', '/register', 'auth_path', 'Registration page', 82)
    insert_pattern('global', 'path', '/signup', 'auth_path', 'Sign up page', 83)
    insert_pattern('global', 'path', '/logout', 'auth_path', 'Logout endpoint', 84)
    insert_pattern('global', 'path', '/account', 'auth_path', 'User account page', 85)
    insert_pattern('global', 'path', '/my-account', 'auth_path', 'User account page', 86)
    insert_pattern('global', 'path', '/dashboard', 'auth_path', 'User dashboard', 87)
    insert_pattern('global', 'path', '/profile', 'auth_path', 'User profile', 88)
    insert_pattern('global', 'path', '/orders', 'auth_path', 'User orders', 89)
    
    # Cart/Checkout paths
    insert_pattern('global', 'path', '/cart', 'cart_path', 'Shopping cart', 90)
    insert_pattern('global', 'path', '/basket', 'cart_path', 'Shopping basket', 91)
    insert_pattern('global', 'path', '/checkout', 'cart_path', 'Checkout page', 92)
    insert_pattern('global', 'path', '/wishlist', 'cart_path', 'Wishlist', 93)
    
    # Password reset
    insert_pattern('global', 'path', '/forgot-password', 'auth_path', 'Password reset', 95)
    insert_pattern('global', 'path', '/reset-password', 'auth_path', 'Password reset', 96)
    
    # Action links
    insert_pattern('global', 'path', '/delete', 'action_link', 'Destructive action link', 100)
    insert_pattern('global', 'path', '/remove', 'action_link', 'Destructive action link', 101)
    insert_pattern('global', 'path', '/add-to-cart', 'action_link', 'Add to cart action', 102)
    insert_pattern('global', 'path', '/add-to-wishlist', 'action_link', 'Add to wishlist action', 103)
    insert_pattern('global', 'path', '/vote', 'action_link', 'Voting action', 104)
    insert_pattern('global', 'path', '/confirm', 'action_link', 'Confirmation action', 105)
    insert_pattern('global', 'path', '/verify', 'action_link', 'Verification action', 106)
    insert_pattern('global', 'path', '/activate', 'action_link', 'Account activation', 107)
    
    # Non-page file extensions - Documents
    insert_pattern('global', 'extension', '.pdf', 'non_page_file', 'PDF document', 110)
    insert_pattern('global', 'extension', '.doc', 'non_page_file', 'Word document', 111)
    insert_pattern('global', 'extension', '.docx', 'non_page_file', 'Word document', 112)
    insert_pattern('global', 'extension', '.xls', 'non_page_file', 'Excel spreadsheet', 113)
    insert_pattern('global', 'extension', '.xlsx', 'non_page_file', 'Excel spreadsheet', 114)
    insert_pattern('global', 'extension', '.ppt', 'non_page_file', 'PowerPoint presentation', 115)
    insert_pattern('global', 'extension', '.pptx', 'non_page_file', 'PowerPoint presentation', 116)
    insert_pattern('global', 'extension', '.csv', 'non_page_file', 'CSV data file', 117)
    insert_pattern('global', 'extension', '.txt', 'non_page_file', 'Text file', 118)
    
    # Non-page file extensions - Images
    insert_pattern('global', 'extension', '.jpg', 'image_file', 'JPEG image', 120)
    insert_pattern('global', 'extension', '.jpeg', 'image_file', 'JPEG image', 121)
    insert_pattern('global', 'extension', '.png', 'image_file', 'PNG image', 122)
    insert_pattern('global', 'extension', '.gif', 'image_file', 'GIF image', 123)
    insert_pattern('global', 'extension', '.webp', 'image_file', 'WebP image', 124)
    insert_pattern('global', 'extension', '.svg', 'image_file', 'SVG image', 125)
    insert_pattern('global', 'extension', '.ico', 'image_file', 'ICO icon', 126)
    
    # Non-page file extensions - Video/Audio
    insert_pattern('global', 'extension', '.mp4', 'video_file', 'MP4 video', 130)
    insert_pattern('global', 'extension', '.mp3', 'audio_file', 'MP3 audio', 131)
    insert_pattern('global', 'extension', '.mov', 'video_file', 'QuickTime video', 132)
    insert_pattern('global', 'extension', '.wav', 'audio_file', 'WAV audio', 133)
    
    # Non-page file extensions - Archives/Assets/Fonts
    insert_pattern('global', 'extension', '.zip', 'archive_file', 'ZIP archive', 140)
    insert_pattern('global', 'extension', '.rar', 'archive_file', 'RAR archive', 141)
    insert_pattern('global', 'extension', '.js', 'asset_file', 'JavaScript asset', 142)
    insert_pattern('global', 'extension', '.css', 'asset_file', 'CSS asset', 143)
    insert_pattern('global', 'extension', '.json', 'asset_file', 'JSON data file', 144)
    insert_pattern('global', 'extension', '.xml', 'technical_file', 'XML sitemap/file', 145)
    insert_pattern('global', 'extension', '.woff', 'font_file', 'WOFF font', 146)
    insert_pattern('global', 'extension', '.woff2', 'font_file', 'WOFF2 font', 147)
    
    # Non-link schemes
    insert_pattern('global', 'scheme', 'mailto', 'non_link_address', 'Email link (mailto)', 150)
    insert_pattern('global', 'scheme', 'tel', 'non_link_address', 'Phone link (tel)', 151)
    insert_pattern('global', 'scheme', 'javascript', 'non_link_address', 'JavaScript URI', 152)
    insert_pattern('global', 'scheme', 'sms', 'non_link_address', 'SMS URI', 153)
    insert_pattern('global', 'scheme', 'data', 'non_link_address', 'Data URI', 154)
    insert_pattern('global', 'scheme', 'blob', 'non_link_address', 'Blob URI', 155)
    
    # Non-production hosts
    insert_pattern('global', 'regex', r'^[0-9]{1,3}(\.[0-9]{1,3}){3}$', 'non_production', 'IP address host', 160)
    insert_pattern('global', 'regex', r'^staging\.', 'non_production', 'Staging environment subdomain', 161)
    insert_pattern('global', 'regex', r'^dev\.', 'non_production', 'Development environment subdomain', 162)
    insert_pattern('global', 'regex', r'^test\.', 'non_production', 'Testing environment subdomain', 163)
    insert_pattern('global', 'regex', r'^beta\.', 'non_production', 'Beta environment subdomain', 164)
    insert_pattern('global', 'regex', r'^uat\.', 'non_production', 'UAT environment subdomain', 165)
    insert_pattern('global', 'host', 'localhost', 'non_production', 'Localhost', 166)
    insert_pattern('global', 'host', '127.0.0.1', 'non_production', 'Localhost IP', 167)
    
    # Print/AMP versions
    insert_pattern('global', 'regex', r'/print', 'print_version', 'Print version of page (?print=1 or /print/)', 170)
    insert_pattern('global', 'regex', r'/amp', 'print_version', 'AMP version of page (/amp or ?amp=1)', 171)
    
    # Technical files
    insert_pattern('global', 'path', '/robots.txt', 'technical_file', 'robots.txt (read separately)', 180)
    insert_pattern('global', 'regex', r'/robots\.txt$', 'technical_file', 'robots.txt at path', 181)
    insert_pattern('global', 'regex', r'/sitemap.*\.xml$', 'technical_file', 'Sitemap XML files', 182)
    insert_pattern('global', 'path', '/favicon.ico', 'technical_file', 'Favicon', 183)
    insert_pattern('global', 'path', '/manifest.json', 'technical_file', 'Web app manifest', 184)
    insert_pattern('global', 'path', '/sw.js', 'technical_file', 'Service worker', 185)
    insert_pattern('global', 'extension', '.webmanifest', 'technical_file', 'Web app manifest file', 186)
    insert_pattern('global', 'regex', r'/feed/?$', 'technical_file', 'RSS/Atom feed', 187)
    insert_pattern('global', 'regex', r'/rss', 'technical_file', 'RSS feed', 188)
    insert_pattern('global', 'regex', r'/atom\.xml$', 'technical_file', 'Atom feed', 189)
    
    # ===== PERFORMANCE PATTERNS =====
    insert_pattern('performance', None, None, 'redirect_source', 'Redirect source — score belongs to destination', 200)
    insert_pattern('performance', None, None, 'error_page', '404/error pages inflate averages', 201)
    insert_pattern('performance', 'path', '/thank-you', 'thank_you_page', 'Thank-you page needs prior action/cookies', 202)
    insert_pattern('performance', 'path', '/order-confirmation', 'thank_you_page', 'Order confirmation needs prior action', 203)
    insert_pattern('performance', 'regex', r'/feed\?page=', 'infinite_scroll', 'Infinite scroll pagination', 204)
    
    # ===== ACCESSIBILITY PATTERNS =====
    insert_pattern('accessibility', None, None, 'redirect_source', 'Test the final page only', 300)
    insert_pattern('accessibility', None, None, 'error_page', 'Test 404 template once only', 301)
    insert_pattern('accessibility', None, None, 'pdf_page', 'PDFs need separate accessibility tooling (Lighthouse can\'t test)', 302)
    insert_pattern('accessibility', None, None, 'third_party_page', 'Cannot fix issues on third-party pages', 303)
    insert_pattern('accessibility', None, None, 'same_template_duplicate', 'Test one page per template', 304)
    insert_pattern('accessibility', None, None, 'popup_content', 'Content in modals/popups needs manual testing', 305)
    insert_pattern('accessibility', 'extension', '.pdf', 'pdf_page', 'PDF files (Lighthouse can\'t test)', 306)
    
    # ===== BEST PRACTICES PATTERNS =====
    insert_pattern('bestpractices', 'scheme', 'http', 'http_version', 'HTTP version redirects to HTTPS', 400)
    insert_pattern('bestpractices', None, None, 'error_page', '404 reported as error by Lighthouse', 401)
    insert_pattern('bestpractices', None, None, 'staging_version', 'HTTPS check doesn\'t apply to staging', 402)
    insert_pattern('bestpractices', None, None, 'same_template_duplicate', 'Shared issues across template', 403)
    insert_pattern('bestpractices', None, None, 'login_required', 'Pages needing login', 404)
    insert_pattern('bestpractices', None, None, 'redirect_source', 'Test the final page', 405)
    
    # ===== SEO PATTERNS =====
    insert_pattern('seo', None, None, 'noindex_page', 'Pages marked noindex on purpose', 500)
    insert_pattern('seo', 'path', '/login', 'noindex_page', 'Login page (noindex by design)', 501)
    insert_pattern('seo', 'path', '/cart', 'noindex_page', 'Cart page', 502)
    insert_pattern('seo', 'path', '/checkout', 'noindex_page', 'Checkout page', 503)
    insert_pattern('seo', 'path', '/thank-you', 'noindex_page', 'Thank-you page', 504)
    insert_pattern('seo', 'path', '/my-account', 'noindex_page', 'Account page', 505)
    insert_pattern('seo', 'regex', r'/lp/.*', 'noindex_page', 'Pay-per-click landing pages', 506)
    insert_pattern('seo', None, None, 'robots_blocked', 'Blocked by robots.txt', 507)
    insert_pattern('seo', None, None, 'non_canonical', 'Non-canonical duplicate', 508)
    insert_pattern('seo', None, None, 'redirect_source', 'Test the final page', 509)
    insert_pattern('seo', None, None, 'internal_search', 'Internal search results', 510)
    insert_pattern('seo', None, None, 'thin_page', 'Auto-generated thin content', 511)
    insert_pattern('seo', None, None, 'pagination_archive', 'Auto-generated archive pages', 512)
    insert_pattern('seo', None, None, 'error_page', 'Error pages', 513)
    insert_pattern('seo', None, None, 'staging_version', 'Staging/dev copies', 514)
    insert_pattern('seo', None, None, 'feed_embed', 'Feeds and embeds', 515)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove pages_skipped column from crawl_jobs
    op.drop_column('crawl_jobs', 'pages_skipped')
    
    # Drop url_ignore_patterns table (indexes and constraints are dropped automatically)
    op.drop_table('url_ignore_patterns')