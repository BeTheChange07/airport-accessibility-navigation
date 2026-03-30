Requires
    fastapi
    uvicorn
    psycpg2-binary
    python-dotenv
    numpy
    scipy

Expected inputs and outputs
    get request
        inputs
            get request with a json containing
                latitude field
                longitude field
        outputs
            json containing
                navigationData
                amenityData
                    format is whatever it is in the DB except as raw json
                amenityUnitsData
                    format is whatever it is in the DB except as raw json
