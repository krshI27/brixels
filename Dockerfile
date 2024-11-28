FROM --platform=${BUILDPLATFORM} ubuntu:latest

USER root
WORKDIR /app

RUN apt update && apt upgrade -y && apt install -y git wget ca-certificates zsh &&\
 chsh -s $(which zsh) &&\
 sh -c "$(wget https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh -O -)"

ARG TARGETPLATFORM
RUN case ${TARGETPLATFORM} in \
        "linux/amd64")  MINI_ARCH=x86_64  ;; \
        "linux/arm64")  MINI_ARCH=aarch64  ;; \
    esac &&\
    mkdir -p /opt/conda &&\
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-${MINI_ARCH}.sh -O /opt/conda/miniconda.sh &&\
    bash /opt/conda/miniconda.sh -b -u -p /opt/conda &&\
    rm /opt/conda/miniconda.sh
ENV PATH /opt/conda/bin:$PATH

RUN conda init zsh &&\
 conda update -n base -c defaults conda &&\
 conda install -n base conda-libmamba-solver &&\
 conda config --set solver libmamba

COPY . /app
RUN --mount=type=cache,target=/opt/conda/pkgs conda env create -f environment.yml
RUN echo "conda activate brixels" >> ~/.zshrc
ENV PATH /opt/conda/envs/brixels/bin:$PATH

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "app.py"]

