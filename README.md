# European Commission Alert System

A monitoring and alerting system for European Commission funding opportunities and calls. This application allows users to set up customized alerts for new funding opportunities that match specific criteria, and receive email notifications when new matching opportunities are discovered.

## Features

- **Customized Alerts**: Create and manage alert criteria through a user-friendly web interface
- **Email Notifications**: Receive automatic email alerts when new matching opportunities are found
- **Scheduling**: Configure check intervals for each alert separately
- **Filtering**: Filter opportunities by type, status, program, deadline dates, and more
- **Keyword Search**: Set keywords to find only the most relevant opportunities
- **Results History**: View past alerts and their matching results
- **Multi-User Support**: Send alerts to multiple email addresses

## Installation

### Prerequisites

- Python 3.9+
- SMTP server access for sending emails

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd European-Commision-alert
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables by creating a `.env` file (see [Environment Variables](#environment-variables) section)

5. Create necessary directories:
```bash
mkdir -p data/alerts
```

## Usage

### Running the application locally

```bash
uvicorn main:app --reload
```

Access the web interface at `http://localhost:8000`

### Setting up an alert

1. Navigate to the web interface
2. Create a new alert by entering a name
3. Configure the alert parameters:
   - Email addresses to notify
   - Check interval (in minutes)
   - Custom alert message template
   - Keywords to match
   - Filter criteria (types, status, program, dates, etc.)
4. Save the alert

The system will automatically begin checking for matching opportunities at the specified interval.

## Configuration

### Alert Configuration

Each alert is configured with the following parameters:

- **Name**: A unique identifier for the alert
- **Emails**: List of email addresses to receive notifications
- **Interval**: Time between checks (in minutes)
- **Message**: Template for email notifications with placeholders for opportunity details
- **Keywords**: Terms to search for in opportunity descriptions
- **Query Parameters**: Filtering criteria like type, status, program, dates, etc.

### Message Template

The message template can contain the following placeholders:

- `{title}`: Opportunity title
- `{summary}`: Brief description
- `{starting_date}`: Start date
- `{deadline}`: Submission deadline
- `{type}`: Opportunity type
- `{status}`: Current status
- `{url}`: Link to the opportunity
- `{identifier}`: Unique identifier
- `{reference}`: Reference number
- `{frameworkProgramme}`: Program framework

HTML formatting is supported in the template.

## Docker

### Running with Docker Compose

1. Make sure Docker and Docker Compose are installed
2. Create `.env` file with required environment variables
3. Run:
```bash
docker-compose up -d
```

The application will be available at `http://localhost:8000`

### Environment Variables

Create a `.env` file with the following variables:

```
APP_GOOGLE_EMAIL=your-email@gmail.com
APP_GOOGLE_PASSWORD=your-app-password
```

Notes:
- For Gmail, you need to generate an app password instead of using your regular password
- Additional environment variables can be added as needed for configuration

## Project Structure

```
.
├── app/                  # Web application
│   ├── routes.py         # FastAPI routes
│   └── templates/        # HTML templates
├── config/               # Configuration files
│   ├── alerts.json       # Alert settings
│   └── config.json       # General configuration
├── data/                 # Data storage
│   └── alerts/           # Alert-specific data
├── src/                  # Core functionality
│   ├── api.py            # EC API client
│   ├── core.py           # Main logic
│   ├── mail.py           # Email functionality
│   └── utils.py          # Utility functions
├── .env                  # Environment variables
├── docker-compose.yml    # Docker Compose configuration
├── Dockerfile            # Docker configuration
├── main.py               # Application entry point
└── requirements.txt      # Python dependencies
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit your changes: `git commit -m 'Add some feature'`
4. Push to the branch: `git push origin feature-name`
5. Submit a pull request

## License

[Specify your license]
