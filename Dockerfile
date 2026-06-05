# Use Miniforge as the base image
FROM condaforge/mambaforge:latest

# Set the working directory inside the container
WORKDIR /usr/src/app

# Copy the environment.yml to the container and create the conda environment
COPY environment.yml .

# Create conda environment from environment.yml (environment.yml defines `name: pcd`)
RUN conda env create -f environment.yml

# Use a bash shell for subsequent RUN/CMD
SHELL ["/bin/bash", "-lc"]

# Copy the entire project into the container
COPY . /usr/src/app

# Expose the port Flask will run on
EXPOSE 5000

# Set environment variables (FLASK_APP points to the 'app' variable inside the package)
ENV FLASK_APP=app:app
ENV FLASK_ENV=development
ENV PYTHONPATH=/usr/src/app

# Default command: run Flask inside the conda environment named 'pcd'
CMD ["conda", "run", "--no-capture-output", "-n", "pcd", "flask", "run", "--host=0.0.0.0", "--port=5000"]