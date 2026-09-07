from pyspark.sql import SparkSession, functions as f
from credentials import Credentials

# --- Config do MinIO (porta 9100 = API S3, a que remapeamos) ---

HADOOP_VER = "3.5.0"

spark = SparkSession\
    .builder\
    .appName("criptoflow-spark")\
    .master("local[*]")\
    .config("spark.jars.packages", f"org.apache.hadoop:hadoop-aws:{HADOOP_VER}")\
    .config("spark.hadoop.fs.s3a.endpoint", Credentials.endpoints()['minio'])\
    .config("spark.hadoop.fs.s3a.access.key", Credentials.minio()['key'])\
    .config("spark.hadoop.fs.s3a.secret.key", Credentials.minio()['secret'])\
    .config("spark.hadoop.fs.s3a.path.style.access", "true")\
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")\
    .getOrCreate()


df = spark.read.parquet("s3a://criptoflow/bronze/mercado/")

print("Linhas na bronze:", df.count())
print("Partições:", df.rdd.getNumPartitions())
df.printSchema()

(df.groupBy("id")
   .agg(f.avg("current_price").alias("preco_medio"), f.count("*").alias("amostras"))
   .orderBy(f.desc("amostras"))
   .show(10))

spark.stop()