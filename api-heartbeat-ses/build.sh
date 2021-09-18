pip install --target ./deploy requests
cd deploy/
zip -r ../deployment-package.zip .
cd ..
zip -g deployment-package.zip lambda_function.py

