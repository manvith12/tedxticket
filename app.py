import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import qrcode
import uuid
import hashlib
import json
import os
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

# --- Configuration ---
TEMPLATE_PATH = "image_0.png"
HASH_DB_FILE = "issued_hashes.json"

# Default QR placement values (can be adjusted via sidebar)
DEFAULT_QR_POS_X = 93
DEFAULT_QR_POS_Y = 393
DEFAULT_QR_SIZE = 313

# --- Helper Functions ---

def load_hash_db():
    if not os.path.exists(HASH_DB_FILE):
        return []
    with open(HASH_DB_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_to_hash_db(new_hash, attendee_info=None):
    """Save hash with optional attendee info for tracking."""
    db_file = HASH_DB_FILE.replace('.json', '_detailed.json')
    
    # Simple list for verification
    simple_db = load_hash_db()
    if new_hash not in simple_db:
        simple_db.append(new_hash)
        with open(HASH_DB_FILE, 'w') as f:
            json.dump(simple_db, f, indent=2)
    
    # Detailed records for tracking
    if attendee_info:
        detailed_db = []
        if os.path.exists(db_file):
            with open(db_file, 'r') as f:
                try:
                    detailed_db = json.load(f)
                except json.JSONDecodeError:
                    detailed_db = []
        
        detailed_db.append({
            "hash": new_hash,
            "email": attendee_info.get("email"),
            "name": attendee_info.get("name"),
            "issued_at": attendee_info.get("issued_at"),
            "invite_code": attendee_info.get("invite_code")
        })
        with open(db_file, 'w') as f:
            json.dump(detailed_db, f, indent=2)

def get_image_dimensions():
    """Get template image dimensions for QR placement UI."""
    try:
        img = Image.open(TEMPLATE_PATH)
        return img.size
    except:
        return (800, 600)  # Default fallback

def generate_ticket_image(invite_code, hashed_data, attendee_name=""):
    """Generate ticket with QR code and text at fixed positions."""
    # Fixed text placement defaults
    NAME_X, NAME_Y, NAME_SIZE = 670, 467, 43
    CODE_X, CODE_Y, CODE_SIZE = 790, 623, 43
    TEXT_COLOR = "white"
    
    base_image = Image.open(TEMPLATE_PATH).convert("RGBA")
    img_width, img_height = base_image.size

    # Generate QR Code with higher error correction for better scanning
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2
    )
    qr.add_data(hashed_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    # Resize QR to fit the default size
    qr_img = qr_img.resize((DEFAULT_QR_SIZE, DEFAULT_QR_SIZE), Image.Resampling.LANCZOS)

    # Use default QR position
    final_x = DEFAULT_QR_POS_X
    final_y = DEFAULT_QR_POS_Y

    # Create a white background for QR code (ensures visibility)
    white_bg = Image.new('RGBA', (DEFAULT_QR_SIZE + 10, DEFAULT_QR_SIZE + 10), (255, 255, 255, 255))
    base_image.paste(white_bg, (final_x - 5, final_y - 5))
    
    # Paste QR code
    base_image.paste(qr_img, (final_x, final_y), qr_img)

    # Draw text (Name and Invite Code) on the ticket
    draw = ImageDraw.Draw(base_image)
    
    # Try to load a nice font, fallback to default
    def get_font(size):
        import subprocess
        import glob
        
        # Known font paths to check first
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/noto/NotoSans-Bold.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Arial.ttf",
        ]
        
        # Try known paths first
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, size)
                except:
                    pass
        
        # Search for any TTF font on Linux
        search_patterns = [
            "/usr/share/fonts/**/*.ttf",
            "/usr/local/share/fonts/**/*.ttf",
            os.path.expanduser("~/.fonts/**/*.ttf"),
            os.path.expanduser("~/.local/share/fonts/**/*.ttf"),
        ]
        
        for pattern in search_patterns:
            fonts = glob.glob(pattern, recursive=True)
            for font_path in fonts:
                try:
                    return ImageFont.truetype(font_path, size)
                except:
                    pass
        
        # Fallback: try to load default with size (Pillow 10.1+)
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            # Older Pillow doesn't support size parameter
            return ImageFont.load_default()
    
    # Draw attendee name if provided
    if attendee_name:
        name_font = get_font(NAME_SIZE)
        draw.text((NAME_X, NAME_Y), attendee_name, fill=TEXT_COLOR, font=name_font)
    
    # Draw invite code
    code_font = get_font(CODE_SIZE)
    draw.text((CODE_X, CODE_Y), invite_code, fill=TEXT_COLOR, font=code_font)

    return base_image

def send_email(to_email, attendee_name, image_data, smtp_server, smtp_port, sender_email, sender_password, invite_code):
    """Actually send email with ticket attachment via SMTP."""
    try:
        # Create message
        msg = MIMEMultipart('related')
        msg['Subject'] = '🎟️ Your TEDx Event Ticket'
        msg['From'] = sender_email
        msg['To'] = to_email

        # HTML email body with embedded image
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #e62b1e 0%, #000000 100%); padding: 30px; border-radius: 10px; text-align: center;">
                <h1 style="color: white; margin: 0;">TEDx Event</h1>
                <p style="color: #ffcccc; margin-top: 10px;">Ideas Worth Spreading</p>
            </div>
            
            <div style="padding: 30px; background: #f9f9f9; border-radius: 0 0 10px 10px;">
                <h2 style="color: #333;">Hello{' ' + attendee_name if attendee_name else ''}! 👋</h2>
                
                <p style="color: #555; line-height: 1.6;">
                    Your ticket for the TEDx event is ready! Please find your personalized ticket attached below.
                </p>
                
                <div style="background: #fff; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #ddd;">
                    <p style="margin: 0; color: #888; font-size: 12px;">YOUR INVITE CODE</p>
                    <p style="margin: 5px 0 0 0; font-size: 24px; font-weight: bold; color: #e62b1e; letter-spacing: 2px;">{invite_code}</p>
                </div>
                
                <p style="color: #555; line-height: 1.6;">
                    <strong>📱 How to use your ticket:</strong><br>
                    1. Save or print the attached ticket image<br>
                    2. Present the QR code at the venue entrance<br>
                    3. Our staff will scan and verify your ticket
                </p>
                
                <p style="color: #555; line-height: 1.6;">
                    <strong>⚠️ Important:</strong> This ticket is unique to you and can only be used once.
                </p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                
                <p style="color: #999; font-size: 12px; text-align: center;">
                    If you didn't request this ticket, please ignore this email.<br>
                    © TEDx Event Ticketing System
                </p>
            </div>
        </body>
        </html>
        """
        
        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)
        
        # Plain text version
        text_body = f"""
        Hello{' ' + attendee_name if attendee_name else ''}!
        
        Your TEDx event ticket is ready!
        
        Invite Code: {invite_code}
        
        Please find your ticket attached. Present the QR code at the venue entrance.
        
        This ticket is unique to you and can only be used once.
        """
        
        msg_alternative.attach(MIMEText(text_body, 'plain'))
        msg_alternative.attach(MIMEText(html_body, 'html'))

        # Attach ticket image
        image_data.seek(0)
        img_attachment = MIMEImage(image_data.read(), name='tedx_ticket.png')
        img_attachment.add_header('Content-Disposition', 'attachment', filename='tedx_ticket.png')
        msg.attach(img_attachment)

        # Connect and send
        if smtp_port == 465:
            # SSL
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            # TLS
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
        
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        return True, "Email sent successfully!"
    
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check your email and app password."
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        return False, f"Error sending email: {str(e)}"

# --- Streamlit App Interface ---

st.set_page_config(page_title="TEDx Ticketing", layout="wide", page_icon="🎫")

# Custom CSS for better styling
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
    }
    .success-box {
        padding: 20px;
        background-color: #d4edda;
        border-radius: 10px;
        border: 1px solid #c3e6cb;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎫 TEDx Event Ticketing System")

# --- Sidebar Configuration ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # Email Configuration
    st.subheader("📧 Email Settings (SMTP)")
    st.info("💡 For Gmail: Use an [App Password](https://myaccount.google.com/apppasswords)")
    
    smtp_server = st.text_input(
        "SMTP Server", 
        value="smtp.gmail.com",
        help="Gmail: smtp.gmail.com | Outlook: smtp.office365.com"
    )
    smtp_port = st.selectbox(
        "SMTP Port",
        [587, 465, 25],
        help="587 (TLS) is recommended for most providers"
    )
    sender_email = st.text_input("Sender Email")
    sender_password = st.text_input("App Password", type="password")
    
    st.divider()
    
    # Preview button
    if st.button("🔍 Preview Ticket"):
        preview_img = generate_ticket_image("ABCD1234", "preview_hash_data", attendee_name="Sample Name")
        st.image(preview_img, caption="Ticket Preview", width=400)

# --- Main Content ---
tab1, tab2, tab3 = st.tabs(["🎫 Generate & Send Ticket", "� Verify Ticket", "📊 Issued Tickets"])

# --- TAB 1: GENERATION ---
with tab1:
    st.header("Issue New Ticket")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        attendee_email = st.text_input("📧 Attendee Email Address", placeholder="attendee@example.com")
        attendee_name = st.text_input("👤 Attendee Name (Optional)", placeholder="John Doe")
        
        generate_btn = st.button("🎫 Generate and Send Ticket", type="primary", use_container_width=True)
    
    with col2:
        st.info("""
        **How it works:**
        1. Enter attendee details
        2. Ticket with unique QR is generated
        3. Email is sent to attendee
        4. QR hash stored for verification
        """)

    if generate_btn:
        if not attendee_email:
            st.error("❌ Please provide an email address.")
        elif not sender_email or not sender_password:
            st.error("❌ Please configure email settings in the sidebar.")
        else:
            with st.spinner("🔄 Generating ticket..."):
                import datetime
                
                # 1. Generate unique invite code
                invite_code = str(uuid.uuid4().hex[:8]).upper()

                # 2. Create hash for security
                hash_object = hashlib.sha256(invite_code.encode())
                secure_hash = hash_object.hexdigest()

                # 3. Save hash to database with attendee info
                save_to_hash_db(secure_hash, {
                    "email": attendee_email,
                    "name": attendee_name,
                    "issued_at": datetime.datetime.now().isoformat(),
                    "invite_code": invite_code
                })

                # 4. Create the ticket image with name and invite code printed
                final_ticket_img = generate_ticket_image(
                    invite_code, secure_hash, attendee_name=attendee_name
                )

                # Show preview
                st.image(final_ticket_img, caption=f"Ticket for {attendee_email}", width=500)

                # Convert image to bytes
                img_byte_arr = io.BytesIO()
                final_ticket_img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)

                # 5. Send Email
                with st.spinner("📤 Sending email..."):
                    success, message = send_email(
                        to_email=attendee_email,
                        attendee_name=attendee_name,
                        image_data=img_byte_arr,
                        smtp_server=smtp_server,
                        smtp_port=smtp_port,
                        sender_email=sender_email,
                        sender_password=sender_password,
                        invite_code=invite_code
                    )
                    if success:
                        st.success(f"✅ {message}")
                    else:
                        st.error(f"❌ {message}")
                        st.warning("You can download the ticket manually:")
                
                # Always offer download option
                img_byte_arr.seek(0)
                st.download_button(
                    label="📥 Download Ticket",
                    data=img_byte_arr,
                    file_name=f"tedx_ticket_{invite_code}.png",
                    mime="image/png"
                )
                
                st.success(f"🎉 Ticket issued! Invite Code: **{invite_code}**")


# --- TAB 2: VERIFICATION ---
with tab2:
    st.header("Verify Ticket at Venue")
    
    invite_code_input = st.text_input("🎫 Enter Invite Code", placeholder="e.g. ABCD1234").upper().strip()
    verify_btn = st.button("🔍 Verify Ticket", type="primary")

    if verify_btn or invite_code_input:
        if not invite_code_input:
            st.warning("Please enter an invite code.")
        else:
            # 1. Create hash of the input code to check against DB
            hash_object = hashlib.sha256(invite_code_input.encode())
            input_hash = hash_object.hexdigest()
            
            issued_hashes = load_hash_db()

            if input_hash in issued_hashes:
                st.balloons()
                st.success(f"✅ **VALID TICKET** - Code {invite_code_input} is verified!")
                
                # Try to find attendee details
                detailed_db_file = HASH_DB_FILE.replace('.json', '_detailed.json')
                if os.path.exists(detailed_db_file):
                    with open(detailed_db_file, 'r') as f:
                        try:
                            detailed_records = json.load(f)
                            attendee = next((r for r in detailed_records if r['hash'] == input_hash), None)
                            if attendee:
                                st.write("---")
                                st.subheader("👤 Attendee Details")
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**Name:** {attendee.get('name', 'N/A')}")
                                    st.write(f"**Email:** {attendee.get('email', 'N/A')}")
                                with col2:
                                    st.write(f"**Issued At:** {attendee.get('issued_at', 'N/A')}")
                        except:
                            pass

                st.divider()
                # Option to mark as used
                st.warning("⚠️ Marking as used will permanently invalidate this code.")
                
                # Use a unique key and check session state for confirmation
                if st.button("Confirm - Mark as Used", type="primary"):
                    issued_hashes.remove(input_hash)
                    with open(HASH_DB_FILE, 'w') as f:
                        json.dump(issued_hashes, f, indent=2)
                    st.success(f"Ticket {invite_code_input} marked as used!")
                    st.balloons()
                    # We don't st.rerun() here so the success message stays visible
            else:
                st.error("❌ **INVALID TICKET** - Code not found in database or already used.")


# --- TAB 3: ISSUED TICKETS ---
with tab3:
    st.header("📊 Issued Tickets Overview")
    
    # Load detailed database
    detailed_db_file = HASH_DB_FILE.replace('.json', '_detailed.json')
    
    if os.path.exists(detailed_db_file):
        with open(detailed_db_file, 'r') as f:
            try:
                detailed_records = json.load(f)
            except json.JSONDecodeError:
                detailed_records = []
        
        if detailed_records:
            import pandas as pd
            df = pd.DataFrame(detailed_records)
            
            # Show stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Tickets Issued", len(detailed_records))
            with col2:
                valid_hashes = load_hash_db()
                st.metric("Valid (Unused)", len(valid_hashes))
            with col3:
                st.metric("Used/Invalidated", len(detailed_records) - len(valid_hashes))
            
            st.divider()
            st.dataframe(df, width="stretch")
            
            # Export option
            csv = df.to_csv(index=False)
            st.download_button(
                "📥 Export to CSV",
                csv,
                "issued_tickets.csv",
                "text/csv"
            )
        else:
            st.info("No tickets issued yet.")
    else:
        simple_db = load_hash_db()
        if simple_db:
            st.metric("Total Valid Tickets", len(simple_db))
            st.caption("Detailed records not available for older tickets.")
        else:
            st.info("No tickets issued yet. Generate your first ticket in the 'Generate & Send Ticket' tab!")