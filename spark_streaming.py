from pyspark.sql import SparkSession, functions as f
from pyspark.sql.types import StructType, StructField, StringType, DoubleType

SPARK_VER = "4.2.0" 

spark = (
    SparkSession.builder
    .appName("criptoflow-streaming")
    .master("local[*]")
    .config("spark.jars.packages", f"org.apache.spark:spark-sql-kafka-0-10_2.13:{SPARK_VER}")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

# 1) lê o topic como uma "tabela infinita"
raw = (spark.readStream
       .format("kafka")
       .option("kafka.bootstrap.servers", "localhost:9092")
       .option("subscribe", "precos-cripto")
       .option("startingOffsets", "earliest")
       .load())

# 2) o Kafka entrega 'value' como bytes -> parse do nosso JSON
schema = StructType([
    StructField("id", StringType()),
    StructField("preco_usd", DoubleType()),
    StructField("ts", DoubleType()),
])
eventos = (raw
    .select(f.from_json(f.col("value").cast("string"), schema).alias("d"))
    .select("d.*")
    .withColumn("event_time", f.to_timestamp(f.from_unixtime("ts"))))

# 3) média por janela de 1 min, por moeda, com watermark de 2 min
agg = (eventos
    .withWatermark("event_time", "2 minutes")
    .groupBy(f.window("event_time", "1 minute"), "id")
    .agg(f.avg("preco_usd").alias("preco_medio")))

# 4) escreve o resultado no console, ao vivo
query = (agg.writeStream
    .outputMode("update")
    .format("console")
    .option("truncate", False)
    .trigger(processingTime="20 seconds")
    .start())

query.awaitTermination()