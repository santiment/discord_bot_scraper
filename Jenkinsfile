podTemplate(label: 'discord-bot-scraper', containers: [
  containerTemplate(name: 'docker', image: 'docker', ttyEnabled: true, command: 'cat', envVars: [
    envVar(key: 'DOCKER_HOST', value: 'tcp://docker-host-docker-host:2375')
  ])
]) {
  node('discord-bot-scraper') {
    stage('Run Build') {
      container('docker') {
        def scmVars = checkout scm

        withCredentials([
          string(
            credentialsId: 'aws_account_id',
            variable: 'aws_account_id'
          )
        ]) {
          def awsRegistry = "${env.aws_account_id}.dkr.ecr.eu-central-1.amazonaws.com"
          docker.withRegistry("https://${awsRegistry}", "ecr:eu-central-1:ecr-credentials") {
            sh "docker build -t ${awsRegistry}/discord-bot-scraper:${env.BRANCH_NAME} -t ${awsRegistry}/discord-bot-scraper:${scmVars.GIT_COMMIT} ."
            sh "docker push ${awsRegistry}/discord-bot-scraper:${env.BRANCH_NAME}"
            sh "docker push ${awsRegistry}/discord-bot-scraper:${scmVars.GIT_COMMIT}"
          }
        }
      }
    }
  }
}
