FROM python:3.12.14-slim-bookworm

ARG HADOOP_VERSION=3.5.0
ARG SPARK_VERSION=4.2.0
ARG APACHE_MIRROR=https://mirrors.huaweicloud.com/apache
ARG APACHE_FALLBACK=https://downloads.apache.org
ARG HADOOP_SHA512=04ab94496cc00c8b7a28d03f6308eff8d2a4e7f37a9da5e8e086e4d6fc990e7a94d661908f6a6136039536efb362614b8aecdef185b5fb8ed588f0b152c7aa16
ARG SPARK_SHA512=3a6559e8546ff387db8fe7a04b8fe4008853b467b972c2e343df8e14a81450534777719fc5d4998dd96519a86fdf9de140cee753c61e2e94db044d5f9555ddc4

RUN sed -i \
      -e 's@deb.debian.org/debian@mirrors.tuna.tsinghua.edu.cn/debian@g' \
      -e 's@security.debian.org/debian-security@mirrors.tuna.tsinghua.edu.cn/debian-security@g' \
      /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl openjdk-17-jdk-headless procps tini && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt

RUN FILE="hadoop-${HADOOP_VERSION}.tar.gz" && \
    PATH_PART="hadoop/common/hadoop-${HADOOP_VERSION}/${FILE}" && \
    (curl -fL --retry 5 --retry-delay 2 \
      "${APACHE_MIRROR}/${PATH_PART}" -o "${FILE}" || \
     curl -fL --retry 5 --retry-delay 2 \
      "${APACHE_FALLBACK}/${PATH_PART}" -o "${FILE}") && \
    echo "${HADOOP_SHA512}  ${FILE}" | sha512sum -c - && \
    tar -xzf "${FILE}" && \
    mv "hadoop-${HADOOP_VERSION}" hadoop && \
    rm "${FILE}"

RUN FILE="spark-${SPARK_VERSION}-bin-hadoop3.tgz" && \
    PATH_PART="spark/spark-${SPARK_VERSION}/${FILE}" && \
    (curl -fL --retry 5 --retry-delay 2 \
      "${APACHE_MIRROR}/${PATH_PART}" -o "${FILE}" || \
     curl -fL --retry 5 --retry-delay 2 \
      "${APACHE_FALLBACK}/${PATH_PART}" -o "${FILE}") && \
    echo "${SPARK_SHA512}  ${FILE}" | sha512sum -c - && \
    tar -xzf "${FILE}" && \
    mv "spark-${SPARK_VERSION}-bin-hadoop3" spark && \
    rm "${FILE}"

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
      -i https://pypi.tuna.tsinghua.edu.cn/simple \
      -r /tmp/requirements.txt

COPY scripts/start-course.sh /usr/local/bin/start-course
RUN chmod +x /usr/local/bin/start-course

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV HADOOP_HOME=/opt/hadoop
ENV HADOOP_CONF_DIR=/opt/hadoop/etc/hadoop
ENV SPARK_HOME=/opt/spark
ENV PYSPARK_PYTHON=python3
ENV PYSPARK_DRIVER_PYTHON=python3
ENV PYTHONPATH=/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.9-src.zip
ENV PATH=/opt/hadoop/bin:/opt/hadoop/sbin:/opt/spark/bin:/usr/local/bin:$PATH

WORKDIR /workspace/backend
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["start-course"]
