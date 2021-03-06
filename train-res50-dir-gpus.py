import torch
from torchvision import datasets, models, transforms
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
import time
 
import numpy as np
import matplotlib.pyplot as plt
import os
from tqdm import tqdm


 #数据增强
image_transforms = {
    'train': transforms.Compose([
        transforms.RandomResizedCrop(size=256, scale=(0.8, 1.0)),
        transforms.RandomRotation(degrees=15),
        transforms.RandomHorizontalFlip(),
        transforms.CenterCrop(size=224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])
    ]),
    'valid': transforms.Compose([
        transforms.Resize(size=256),
        transforms.CenterCrop(size=224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])
    ])
}

#加载数据
dataset = 'flowers102'
train_directory = os.path.join(dataset, 'train')
valid_directory = os.path.join(dataset, 'valid')
 
batch_size = 256
num_classes = 102
device_ids = [0,1,2,3,4,5,6,7]

data = {
    'train': datasets.ImageFolder(root=train_directory, transform=image_transforms['train']),
    'valid': datasets.ImageFolder(root=valid_directory, transform=image_transforms['valid'])
 
}
 
 
train_data_size = len(data['train'])
valid_data_size = len(data['valid'])
 
train_data = DataLoader(data['train'], batch_size=batch_size, shuffle=True,num_workers=32)
valid_data = DataLoader(data['valid'], batch_size=batch_size, shuffle=True,num_workers=32)
 
print(train_data_size, valid_data_size)

#迁移学习
resnet50 = models.resnet50(pretrained=True)
for param in resnet50.parameters():
    param.requires_grad = False

#修改最后的fc层
fc_inputs = resnet50.fc.in_features
resnet50.fc = nn.Sequential(
    nn.Linear(fc_inputs, 256),
    nn.ReLU(),
    nn.Dropout(0.4),
    nn.Linear(256, 10),
    nn.LogSoftmax(dim=1)
)
#使用gpu训练
resnet50 = torch.nn.DataParallel(resnet50, device_ids=device_ids) # 声明所有可用设备
resnet50 = resnet50.cuda(device=device_ids[0])  # 模型放在主设备
#定义损失函数和优化器
loss_func = nn.CrossEntropyLoss()
optimizer = optim.Adam(resnet50.parameters())


#训练
def train_and_valid(model, loss_function, optimizer, epochs=25):
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    history = []
    best_acc = 0.0
    best_epoch = 0
 
    for epoch in range(epochs):
        epoch_start = time.time()
        print("Epoch: {}/{}".format(epoch+1, epochs))

        train_loss = 0.0
        train_acc = 0.0
        valid_loss = 0.0
        valid_acc = 0.0
        for data in tqdm(train_data):
            inputs, labels = data
            # 注意数据也是放在主设备
            inputs, labels = inputs.cuda(device=device_ids[0]), labels.cuda(device=device_ids[0])

            outputs = resnet50(inputs)
            _, pred = torch.max(outputs.data, 1)
            optimizer.zero_grad()
            loss = loss_func(outputs, labels)

            loss.backward()
            optimizer.step()
            train_loss += loss.data.item()
            train_acc += torch.sum(pred == labels.data)
	with torch.no_grad():
		resnet50.eval()
		for data in valid_data:
		    inputs, labels = data
		    inputs, labels = inputs.cuda(device=device_ids[0]), labels.cuda(device=device_ids[0])
		    outputs = resnet50(inputs)
		    loss=loss_func(outputs,labels)
		    _, pred = torch.max(outputs.data, 1)
		    valid_loss+=loss.item()
		    valid_acc += torch.sum(pred == labels.data)

        avg_train_loss = train_loss/train_data_size
        avg_train_acc = train_acc.to(torch.float32)/train_data_size
 
        avg_valid_loss = valid_loss/valid_data_size
        avg_valid_acc = valid_acc.to(torch.float32)/valid_data_size
 
        history.append([avg_train_loss, avg_valid_loss, avg_train_acc, avg_valid_acc])
 
        if best_acc < avg_valid_acc:
            best_acc = avg_valid_acc
            best_epoch = epoch + 1
 
        epoch_end = time.time()
 
        print("Epoch: {:03d}, Training: Loss: {:.4f}, Accuracy: {:.4f}%, \n\t\tValidation: Loss: {:.4f}, Accuracy: {:.4f}%, Time: {:.4f}s".format(
            epoch+1, avg_valid_loss, avg_train_acc*100, avg_valid_loss, avg_valid_acc*100, epoch_end-epoch_start
        ))
        print("Best Accuracy for validation : {:.4f} at epoch {:03d}".format(best_acc, best_epoch))
 
        torch.save(model, 'models/'+dataset+'_model_'+str(epoch+1)+'.pt')
    return model, history

	

#执行体
num_epochs = 30
trained_model, history = train_and_valid(resnet50, loss_func, optimizer, num_epochs)
torch.save(history, 'models/'+dataset+'_history.pt')
 
history = np.array(history)
plt.plot(history[:, 0:2])
plt.legend(['Tr Loss', 'Val Loss'])
plt.xlabel('Epoch Number')
plt.ylabel('Loss')
plt.ylim(0, 1)
plt.savefig(dataset+'_loss_curve.png')
plt.show()
 
plt.plot(history[:, 2:4])
plt.legend(['Tr Accuracy', 'Val Accuracy'])
plt.xlabel('Epoch Number')
plt.ylabel('Accuracy')
plt.ylim(0, 1)
plt.savefig(dataset+'_accuracy_curve.png')
plt.show()
